"""Writes results.json, results.csv (one row per model), generations.csv (one row per call)
and report.md."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from banana_english.benchmark.scoring import (
    DIMENSIONS,
    PERFORMANCE_WEIGHT,
    QUALITY_WEIGHT,
    paired_difference,
)

SUMMARY_COLUMNS = (
    "model",
    "quality",
    "performance",
    "overall",
    "latency_p50_s",
    "latency_p95_s",
    "latency_mean_s",
    "ttft_p50_s",
    "ttft_p95_s",
    "tokens_per_s",
    "output_tokens_mean",
    "memory_gb",
    "vram_gb",
    "load_s",
    "requests",
    "errors",
    "contract_failures",
    *(f"dim_{d}" for d in DIMENSIONS),
)
GEN_COLUMNS = (
    "model",
    "test_id",
    "category",
    "run",
    "ttft_s",
    "total_s",
    "output_tokens",
    "input_tokens",
    "tokens_per_s",
    "contract_ok",
    "score",
    "error",
)


def write_all(result: dict, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / "results.json", out / "results.csv", out / "generations.csv", out / "report.md"]
    paths[0].write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with paths[1].open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, SUMMARY_COLUMNS)
        w.writeheader()
        for s in result["summary"]:
            row = {k: s.get(k) for k in SUMMARY_COLUMNS if not k.startswith("dim_")}
            row.update({f"dim_{d}": s["dimensions"].get(d) for d in DIMENSIONS})
            w.writerow(row)
    with paths[2].open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, GEN_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for g in result["generations"]:
            w.writerow({k: _round(g.get(k)) for k in GEN_COLUMNS})
    paths[3].write_text(render_markdown(result), encoding="utf-8")
    return paths


def recommendation(summary: list[dict]) -> str:
    if not summary:
        return "No model could be benchmarked."
    best = summary[0]
    text = (
        f"**{best['model']}** has the highest overall score ({best['overall']}: quality "
        f"{best['quality']}, performance {best['performance']})."
    )
    if len(summary) > 1:
        second = summary[1]
        diff, ci, n = paired_difference(best.get("test_scores", {}), second.get("test_scores", {}))
        versus = (
            f" Paired over {n} tests, its mean test score differs from {second['model']} "
            f"by {diff:+.1f} (95% CI ±{ci:.1f})"
        )
        if n < 2:
            text += f" Too few tests to compare it with {second['model']}."
        elif abs(diff) <= ci:
            text += (
                versus + ": not a significant quality difference, so speed and memory "
                "should decide between them."
            )
        else:
            text += versus + ": a significant difference."
    return text


def render_markdown(r: dict) -> str:
    summary = r["summary"]
    cfg = r["config"]
    host = r["host"]
    cpu_only = all((s.get("vram_gb") or 0) == 0 for s in summary)
    lines = [
        "# Banana English LLM benchmark",
        "",
        f"- Run: {r['started_at']} → {r['finished_at']} ({r['duration_min']} min), suite "
        f"**{r['suite']}**, dataset `{r['dataset_version']}` ({cfg['tests']} tests × "
        f"{cfg['runs']} runs per model; before every run the model is reloaded and gets "
        f"{cfg['warmup']} warm-up calls)",
        f"- Host: {host['cpu']}, {host['logical_cpus']} logical CPUs, {host['ram_gb']} GB RAM; "
        f"Ollama {host['ollama_version']}"
        + ("; **CPU inference** (Ollama reports 0 GB in VRAM for every model)" if cpu_only else ""),
        f"- Same for every model: prompts {', '.join(cfg['prompt_versions'])}; production "
        f"temperature and token limits per task; num_ctx {cfg['num_ctx']}; seeds {cfg['seeds']}; "
        f"sampling {_kv(cfg.get('sampling', {}))}; chat template of "
        f"`{cfg.get('reference_template') or 'each model'}`; thinking off; same test order; "
        "each model alone in memory.",
        "",
        "## Results",
        "",
        "| Model | Quality | P50 | P95 | Tok/s | VRAM | Overall |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summary:
        vram = s.get("vram_gb")
        vram_txt = (
            "—"
            if vram is None
            else f"{vram:.1f} GB"
            + (f" (RAM {s['memory_gb']:.1f} GB)" if vram == 0 and s.get("memory_gb") else "")
        )
        lines.append(
            f"| {s['model']} | {s['quality']:.1f} | {_s(s['latency_p50_s'])} | "
            f"{_s(s['latency_p95_s'])} | {_n(s['tokens_per_s'])} | {vram_txt} | "
            f"**{s['overall']:.1f}** |"
        )
    lines += [
        "",
        f"Overall = {QUALITY_WEIGHT:.0%} quality + {PERFORMANCE_WEIGHT:.0%} performance. "
        "Performance = 50% speed (fastest P50 ÷ this P50) + 50% throughput "
        "(tok/s ÷ fastest tok/s), "
        "relative to the models in this run. P50/P95 = end-to-end latency per request.",
        "",
        "### Recommendation",
        "",
        recommendation(summary),
        "",
        "### Latency, throughput and memory",
        "",
        "| Model | TTFT P50 | TTFT P95 | Mean latency | Mean output tokens | Memory | Load "
        "| Errors | Invalid replies |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summary:
        lines.append(
            f"| {s['model']} | {_s(s['ttft_p50_s'])} | {_s(s['ttft_p95_s'])} | "
            f"{_s(s['latency_mean_s'])} | {_n(s['output_tokens_mean'])} | "
            f"{_n(s.get('memory_gb'))} GB | {_s(s.get('load_s'))} | {s['errors']} | "
            f"{s['contract_failures']} |"
        )
    lines += [
        "",
        "### Quality by rubric dimension (0–100)",
        "",
        "| Model | " + " | ".join(d.replace("_", " ") for d in DIMENSIONS) + " | Quality by run |",
        "|---|" + "---:|" * len(DIMENSIONS) + "---|",
    ]
    for s in summary:
        dims = " | ".join(_n(s["dimensions"].get(d)) for d in DIMENSIONS)
        lines.append(f"| {s['model']} | {dims} | {', '.join(map(str, s['quality_by_run']))} |")
    cats = sorted({c for s in summary for c in s["categories"]})
    lines += [
        "",
        "### Quality by category (mean test score, 0–100)",
        "",
        "| Model | " + " | ".join(c.replace("_", " ") for c in cats) + " |",
        "|---|" + "---:|" * len(cats),
    ]
    for s in summary:
        lines.append(
            f"| {s['model']} | " + " | ".join(_n(s["categories"].get(c)) for c in cats) + " |"
        )
    lines += [
        "",
        "### Models",
        "",
        "| Model | Status | Ollama name | Source | Size | Template |",
        "|---|---|---|---|---:|---|",
    ]
    for a in r["availability"]:
        lines.append(
            f"| {a['label']} | {a['status']}{' — ' + a['detail'] if a['detail'] else ''} | "
            f"`{a['tag'] or '—'}` | {a['source']} | {_n(a['size_gb'])} GB | "
            f"`{a['template_digest'] or '—'}` |"
        )
    lines += [
        "",
        "## Method and limits",
        "",
        "- Requests are captured from the production services (grammar assessment, tutor, "
        "conversation partner, AI Monkey), so the benchmark measures the prompts the app sends. "
        "Vocabulary cards and complex questions have no production prompt; they use the "
        "benchmark prompts in `tasks.py`.",
        "- Quality is scored by deterministic checks (see `dataset.json`): valid output contract, "
        "correct verdict and correction against reviewed answers, required concepts, format and "
        "length limits, staying in role, no reasoning leak. They are reproducible but do not "
        "replace a teacher's judgement of nuance.",
        "- Models imported from Hugging Face ship a different chat template (it ignores "
        "think=false) and other default parameters (presence_penalty 1.5). They are benchmarked "
        "through a local alias with the reference model's template and defaults (same weights, "
        "no copy), and every request sends the same sampling options, so only the weights "
        "differ between models.",
        "- Grammar-correction labels come from the calibration set; they were drafted by an AI "
        "and are not yet teacher-verified.",
        "- TTFT is measured on the client (request sent → first streamed token) and includes "
        "prompt processing; tok/s is Ollama's decode rate (output tokens ÷ decode time).",
        "- Ollama caches the KV state of recent prompts. Each run therefore starts from a "
        "reloaded model (warm-up requests are not in the dataset), so no run is answered from "
        "an earlier run's cache; within a run, tests of the same task reuse their shared system "
        "prompt, as production requests do.",
        "- Scores are relative to this hardware and this run; rerun after changing prompts, "
        "Ollama or hardware.",
        f"- Models loaded before the run (unloaded for fairness, reloaded on next use): "
        f"{', '.join(r['models_loaded_before_run']) or 'none'}.",
        "",
    ]
    return "\n".join(lines)


def _kv(d: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in d.items()) or "model defaults"


def _s(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f} s"


def _n(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f}"


def _round(v):
    return round(v, 3) if isinstance(v, float) else v
