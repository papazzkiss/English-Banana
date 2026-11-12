"""Runs the benchmark: availability check, warm-up, N measured runs per test, aggregation.

Fairness rules: every model gets the same requests (built once from production code), the same
options (context size, per-run seed, production temperature and token limit), the same test
order, and starts alone in memory (every other model is unloaded first, the production model
included; it reloads on its next request). The production model setting is never changed.
"""

from __future__ import annotations

import hashlib
import os
import platform
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from banana_english.benchmark.client import Generation, OllamaBenchClient
from banana_english.benchmark.dataset import load_dataset, select, validate
from banana_english.benchmark.scoring import (
    CheckResult,
    dimension_scores,
    overall_score,
    percentile,
    performance_scores,
    quality_score,
    run_check,
    weighted_pass,
)
from banana_english.benchmark.tasks import build_request, parse_output
from banana_english.domain.interfaces.llm import LLMMessage, LLMRequest
from banana_english.domain.interfaces.repositories import ContentRepository


@dataclass(frozen=True)
class ModelSpec:
    label: str
    quantization: str
    candidates: tuple[str, ...]  # Ollama names, tried in order
    source: str


# Ollama's library has no q5_K_M / q6_K tags for qwen3:8b (registry answers 404), so those two
# come from Qwen's official GGUF repository on Hugging Face (pulled through Ollama).
_HF = "huggingface Qwen/Qwen3-8B-GGUF"
DEFAULT_MODELS = (
    ModelSpec("Qwen3-8B Q4_K_M", "Q4_K_M", ("qwen3:8b-q4_K_M", "qwen3:8b"), "ollama library"),
    ModelSpec(
        "Qwen3-8B Q5_K_M",
        "Q5_K_M",
        ("hf.co/Qwen/Qwen3-8B-GGUF:Q5_K_M",),
        "huggingface Qwen/Qwen3-8B-GGUF",
    ),
    ModelSpec(
        "Qwen3-8B Q6_K",
        "Q6_K",
        ("hf.co/Qwen/Qwen3-8B-GGUF:Q6_K",),
        "huggingface Qwen/Qwen3-8B-GGUF",
    ),
    ModelSpec("Qwen3-8B Q8_0", "Q8_0", ("qwen3:8b-q8_0",), "ollama library"),
)


WARMUP_REQUEST = LLMRequest(
    task="bench_warmup",
    prompt_version="bench_warmup_v1",
    messages=(
        LLMMessage("system", "You are a helpful assistant."),
        LLMMessage("user", "Describe a banana in one short sentence."),
    ),
    temperature=0.0,
    max_output_tokens=32,
)


# Sampling options sent with every request, identical for every model: the defaults of
# Ollama's qwen3 library models. Models imported from Hugging Face ship other defaults
# (presence_penalty 1.5), which would otherwise make the comparison unfair. (This offline
# benchmark compares Qwen3-8B quantisations by default; production runs Qwen3-30B-A3B,
# docs/QWEN3_30B.md.)
SAMPLING = {
    "top_k": 20,
    "top_p": 0.95,
    "min_p": 0.0,
    "repeat_penalty": 1.0,
    "presence_penalty": 0.0,
}
# Chat template reference: a model with a different template (e.g. a GGUF from Hugging Face,
# whose template ignores think=false) is benchmarked through a local alias that uses this
# model's template, so only the weights differ.
REFERENCE_MODEL = "qwen3:8b"


@dataclass
class BenchConfig:
    suite: str = "quick"
    runs: int = 3
    warmup: int = 2
    num_ctx: int = 4096
    base_seed: int = 42
    pull: bool = False
    models: tuple[ModelSpec, ...] = DEFAULT_MODELS
    test_ids: tuple[str, ...] = ()  # optional filter (smoke tests)
    settle_s: float = 1.0  # pause after unloading a model
    reference_model: str | None = REFERENCE_MODEL  # None: keep every model's own template


@dataclass
class Availability:
    label: str
    quantization: str
    source: str
    status: str  # "ok" | "missing" | "wrong_quantization" | "error"
    tag: str | None = None
    detail: str = ""
    size_gb: float | None = None
    parameter_size: str | None = None
    template_digest: str | None = None
    aligned_from: str | None = None  # original name when benchmarked through an alias


@dataclass
class GenRow:
    model: str
    test_id: str
    category: str
    run: int
    ttft_s: float | None
    total_s: float
    output_tokens: int | None
    input_tokens: int | None
    tokens_per_s: float | None
    error: str | None
    contract_ok: bool
    score: float
    checks: list[dict] = field(default_factory=list)
    output: str = ""


def _resolve(client: OllamaBenchClient, spec: ModelSpec, pull: bool, log) -> Availability:
    avail = Availability(spec.label, spec.quantization, spec.source, "missing")
    installed = client.installed()
    tag = next((c for c in spec.candidates if c in installed), None)
    if tag is None and pull:
        for candidate in spec.candidates:
            log(f"pulling {candidate} …")
            if client.pull(candidate, log):
                tag = candidate
                break
    if tag is None:
        avail.detail = f"not installed ({', '.join(spec.candidates)})" + (
            "; pull failed" if pull else ""
        )
        return avail
    try:
        info = client.show(tag)
    except Exception as exc:  # noqa: BLE001 - reported, never hidden
        avail.status, avail.tag, avail.detail = "error", tag, f"show failed: {exc}"
        return avail
    details = info.get("details", {})
    quant = details.get("quantization_level", "?")
    avail.tag = tag
    avail.parameter_size = details.get("parameter_size")
    avail.template_digest = _digest(info.get("template", ""))
    avail.size_gb = round(client.sizes().get(tag, 0) / 1e9, 2) or None
    if quant.upper() != spec.quantization.upper():
        avail.status, avail.detail = "wrong_quantization", f"{tag} is {quant}"
        return avail
    avail.status = "ok"
    return avail


def _align_template(client: OllamaBenchClient, avail: Availability, reference: str, log) -> None:
    """Benchmark `avail` through an alias with the reference model's template if they differ."""
    ref = client.show(reference)
    ref_digest = _digest(ref.get("template", ""))
    if avail.template_digest == ref_digest or not avail.tag:
        return
    alias = "bench/" + avail.tag.split("/")[-1].replace(":", "-").lower() + ":aligned"
    params = {**client.parameters(reference), "presence_penalty": 0}
    log(f"{avail.label}: template differs from {reference}; using alias {alias}")
    client.create_alias(alias, avail.tag, ref.get("template", ""), params)
    avail.aligned_from, avail.tag = avail.tag, alias
    avail.template_digest = _digest(client.show(alias).get("template", ""))
    avail.detail = f"weights of {avail.aligned_from}, template + defaults of {reference}"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def run_benchmark(
    config: BenchConfig, client: OllamaBenchClient, content: ContentRepository, log=print
) -> dict:
    dataset = load_dataset()
    problems = validate(dataset["tests"])
    if problems:
        raise ValueError("invalid dataset: " + "; ".join(problems))
    tests = select(dataset["tests"], config.suite)
    if config.test_ids:
        tests = [t for t in tests if t["id"] in config.test_ids]
    requests = {t["id"]: build_request(t, content) for t in tests}
    started_at = datetime.now(UTC)

    availability = [_resolve(client, spec, config.pull, log) for spec in config.models]
    if config.reference_model and config.reference_model in client.installed():
        for a in availability:
            if a.status == "ok":
                try:
                    _align_template(client, a, config.reference_model, log)
                except Exception as exc:  # noqa: BLE001 - reported, the model is then skipped
                    a.status, a.detail = "error", f"template alignment failed: {exc}"
    for a in availability:
        log(f"{a.label}: {a.status} {a.tag or ''} {a.detail}")
    runnable = [a for a in availability if a.status == "ok"]
    initially_loaded = [m.name for m in client.loaded()]

    rows: list[GenRow] = []
    per_model: dict[str, dict] = {}
    total_calls = len(runnable) * len(tests) * config.runs
    done = 0
    t_bench = time.perf_counter()
    for a in runnable:
        assert a.tag
        client.unload_all()
        warmup_errors: list[str] = []
        for run in range(1, config.runs + 1):
            # Every run starts from a freshly loaded model, warmed up with a request that is NOT
            # in the dataset: Ollama keeps the KV cache of recent prompts, so without the reload
            # runs 2+ would answer from the previous run's cache (near-zero TTFT) — not what
            # production sees. Inside a run, tests of one task share their system prompt, as in
            # production.
            client.unload(a.tag)
            time.sleep(config.settle_s)
            log(f"\n=== {a.label} ({a.tag}) run {run} — reload + warm-up ×{config.warmup}")
            warm: list[Generation] = [
                client.generate(
                    a.tag, WARMUP_REQUEST, {**SAMPLING, "num_ctx": config.num_ctx, "seed": 0}
                )
                for _ in range(config.warmup)
            ]
            warmup_errors += [w.error for w in warm if w.error]
            if run == 1 and warm and all(w.error for w in warm):
                # The model cannot even load (e.g. not enough memory): report it, never score it.
                a.status, a.detail = "error", f"failed to load: {warm[-1].error}"
                log(f"{a.label}: {a.detail}")
                break
            if run == 1:
                mem = next((m for m in client.loaded() if m.name == a.tag), None)
                per_model[a.label] = {
                    "load_s": warm[0].load_s if warm else None,
                    "memory_gb": round(mem.size_bytes / 1e9, 2) if mem else None,
                    "vram_gb": round(mem.vram_bytes / 1e9, 2) if mem else None,
                }
            per_model[a.label]["warmup_errors"] = warmup_errors
            options = {**SAMPLING, "num_ctx": config.num_ctx, "seed": config.base_seed + run}
            for t in tests:
                gen = client.generate(a.tag, requests[t["id"]], options)
                if gen.error:  # a failed request fails every check of its test
                    parsed_ok = False
                    results = [
                        CheckResult(
                            c["type"], c["dim"], float(c.get("weight", 1)), False, "request failed"
                        )
                        for c in t["checks"]
                    ]
                else:
                    parsed = parse_output(t, gen.text, content)
                    results = [run_check(c, parsed) for c in t["checks"]]
                    parsed_ok = parsed.contract_ok
                score = weighted_pass(results)
                checks = [asdict(r) for r in results]
                rows.append(
                    GenRow(
                        a.label,
                        t["id"],
                        t["category"],
                        run,
                        gen.ttft_s,
                        gen.total_s,
                        gen.output_tokens,
                        gen.input_tokens,
                        gen.tokens_per_s,
                        gen.error,
                        parsed_ok,
                        score,
                        checks,
                        gen.text,
                    )
                )
                done += 1
                elapsed = time.perf_counter() - t_bench
                eta = elapsed / done * (total_calls - done)
                log(
                    f"[{done}/{total_calls}] {a.label} run{run} {t['id']:6} "
                    f"{gen.total_s:6.1f}s ttft={_fmt(gen.ttft_s)}s tok={gen.output_tokens} "
                    f"score={score:5.1f}{' ERROR ' + gen.error if gen.error else ''}"
                    f"  eta {eta / 60:.0f} min"
                )
        client.unload(a.tag)

    summary = summarise(rows, per_model, [a.label for a in runnable if a.status == "ok"])
    return {
        "benchmark": "banana_english.benchmark",
        "dataset_version": dataset["version"],
        "dataset_notes": dataset["notes"],
        "suite": config.suite,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "duration_min": round((time.perf_counter() - t_bench) / 60, 1),
        "config": {
            "runs": config.runs,
            "warmup": config.warmup,
            "num_ctx": config.num_ctx,
            "seeds": [config.base_seed + r for r in range(1, config.runs + 1)],
            "sampling": SAMPLING,
            "reference_template": config.reference_model,
            "tests": len(tests),
            "test_ids": [t["id"] for t in tests],
            "prompt_versions": sorted({r.prompt_version for r in requests.values()}),
        },
        "host": host_info(client),
        "models_loaded_before_run": initially_loaded,
        "availability": [asdict(a) for a in availability],
        "summary": summary,
        "generations": [asdict(r) for r in rows],
    }


def summarise(rows: list[GenRow], per_model: dict[str, dict], labels: list[str]) -> list[dict]:
    by_model: dict[str, list[GenRow]] = defaultdict(list)
    for r in rows:
        by_model[r.model].append(r)
    stats = {}
    for label in labels:
        rs = by_model[label]
        ok = [r for r in rs if not r.error]
        totals = [r.total_s for r in ok]
        ttfts = [r.ttft_s for r in ok if r.ttft_s is not None]
        tokens = sum(r.output_tokens or 0 for r in ok)
        decode_s = sum((r.output_tokens or 0) / r.tokens_per_s for r in ok if r.tokens_per_s)
        results = [CheckResult(**c) for r in rs for c in r.checks]
        dims = dimension_scores(results)
        categories = defaultdict(list)
        per_test = defaultdict(list)
        for r in rs:
            categories[r.category].append(r.score)
            per_test[r.test_id].append(r.score)
        runs = defaultdict(list)
        for r in rs:
            runs[r.run].append(r)
        run_quality = [
            round(
                quality_score(
                    dimension_scores(CheckResult(**c) for r in run_rows for c in r.checks)
                ),
                1,
            )
            for _, run_rows in sorted(runs.items())
        ]
        stats[label] = {
            "model": label,
            "requests": len(rs),
            "errors": sum(1 for r in rs if r.error),
            "contract_failures": sum(1 for r in rs if not r.error and not r.contract_ok),
            "quality": round(quality_score(dims), 1),
            "quality_by_run": run_quality,
            "dimensions": {d: (round(v, 1) if v is not None else None) for d, v in dims.items()},
            "categories": {c: round(sum(v) / len(v), 1) for c, v in sorted(categories.items())},
            "test_scores": {t: round(sum(v) / len(v), 2) for t, v in per_test.items()},
            "ttft_p50_s": _r(percentile(ttfts, 50)),
            "ttft_p95_s": _r(percentile(ttfts, 95)),
            "latency_p50_s": _r(percentile(totals, 50)),
            "latency_p95_s": _r(percentile(totals, 95)),
            "latency_mean_s": _r(sum(totals) / len(totals) if totals else None),
            "tokens_per_s": _r(tokens / decode_s if decode_s else None),
            "output_tokens_mean": _r(tokens / len(ok) if ok else None),
            **per_model.get(label, {}),
        }
    perf = performance_scores(
        {k: (v["latency_p50_s"], v["tokens_per_s"]) for k, v in stats.items()}
    )
    for label, s in stats.items():
        s["performance"] = round(perf[label], 1)
        s["overall"] = round(overall_score(s["quality"], perf[label]), 1)
    return sorted(stats.values(), key=lambda s: s["overall"], reverse=True)


def host_info(client: OllamaBenchClient) -> dict:
    cpu = "?"
    mem_gb = None
    try:
        with open("/proc/cpuinfo") as f:
            cpu = next(
                (ln.split(":", 1)[1].strip() for ln in f if ln.startswith("model name")), cpu
            )
        with open("/proc/meminfo") as f:
            total = next((ln for ln in f if ln.startswith("MemTotal")), None)
            mem_gb = round(int(total.split()[1]) / 1024 / 1024, 1) if total else None
    except OSError:
        pass
    return {
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "ram_gb": mem_gb,
        "platform": platform.platform(),
        "ollama_version": client.version(),
    }


def _r(v: float | None, n: int = 2) -> float | None:
    return round(v, n) if v is not None else None


def _fmt(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "—"
