"""CLI: python -m banana_english.benchmark [--suite quick|full] [options]

Examples
    python -m banana_english.benchmark --suite quick                 # smoke: 6 tests x 3 runs
    python -m banana_english.benchmark --suite full --pull           # 48 tests x 3 runs
    python -m banana_english.benchmark --models "Q4=qwen3:8b" --runs 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from banana_english.benchmark.client import OllamaBenchClient
from banana_english.benchmark.report import recommendation, write_all
from banana_english.benchmark.runner import DEFAULT_MODELS, BenchConfig, ModelSpec, run_benchmark
from banana_english.config.settings import PROJECT_ROOT, Settings
from banana_english.infrastructure.content.json_content_repository import JsonContentRepository


def parse_models(text: str) -> tuple[ModelSpec, ...]:
    """'Label=tag[|tag2]:QUANT,...' e.g. 'Qwen3-8B Q4_K_M=qwen3:8b@Q4_K_M'."""
    specs = []
    for item in filter(None, (p.strip() for p in text.split(","))):
        label, _, rest = item.partition("=")
        tags, _, quant = rest.rpartition("@")
        if not (label and tags and quant):
            raise argparse.ArgumentTypeError(f"bad model spec {item!r}; use Label=tag@QUANT")
        specs.append(ModelSpec(label, quant, tuple(tags.split("|")), "cli"))
    return tuple(specs)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m banana_english.benchmark",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--suite", choices=("quick", "full"), default="quick")
    p.add_argument("--runs", type=int, default=3, help="measured runs per test (default 3)")
    p.add_argument("--warmup", type=int, default=2, help="unmeasured calls per model first")
    p.add_argument("--num-ctx", type=int, default=4096)
    p.add_argument("--seed", type=int, default=42, help="run i uses seed + i")
    p.add_argument("--pull", action="store_true", help="pull missing models first")
    p.add_argument(
        "--models",
        type=parse_models,
        default=DEFAULT_MODELS,
        help="Label=tag@QUANT,... (default: Qwen3-8B Q4_K_M, Q5_K_M, Q6_K, Q8_0)",
    )
    p.add_argument("--tests", default="", help="comma-separated test ids (subset of the suite)")
    p.add_argument("--out", type=Path, default=None, help="default: benchmarks/results/<suite>")
    p.add_argument("--ollama-url", default=None, help="default: BANANA_OLLAMA_URL")
    p.add_argument("--timeout", type=float, default=900.0, help="seconds per request")
    args = p.parse_args(argv)

    if args.runs < 1:
        p.error("--runs must be >= 1")
    settings = Settings()
    client = OllamaBenchClient(args.ollama_url or settings.ollama_url, timeout_s=args.timeout)
    content = JsonContentRepository(settings.content_dir)
    config = BenchConfig(
        suite=args.suite,
        runs=args.runs,
        warmup=args.warmup,
        num_ctx=args.num_ctx,
        base_seed=args.seed,
        pull=args.pull,
        models=args.models,
        test_ids=tuple(filter(None, args.tests.split(","))),
    )
    result = run_benchmark(config, client, content)
    out = args.out or PROJECT_ROOT / "benchmarks/results" / args.suite
    paths = write_all(result, out)
    print("\n" + recommendation(result["summary"]).replace("**", ""))
    for path in paths:
        print(f"wrote {path}")
    return 0 if result["summary"] else 2


if __name__ == "__main__":
    sys.exit(main())
