"""Phase 3 calibration + prompt regression check against a real model.

    uv run python scripts/calibrate.py                     # compare with labels + baseline
    uv run python scripts/calibrate.py --update-baseline   # accept current scores as baseline

Writes docs/calibration/latest.json and docs/calibration/report.md. CI (tests/unit/
test_calibration_gate.py) fails if the grammar prompt version changed without re-running this.
Uses BANANA_LLM_PROVIDER (default here: ollama) and BANANA_OLLAMA_MODEL (required, e.g.
qwen3:30b-a3b-q4_K_M).
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime

from banana_english.application.services.calibration import (
    DRIFT_TOLERANCE,
    rows_as_dicts,
    run_calibration,
    summarise,
)
from banana_english.application.services.grammar_assessment import LLMGrammarAssessmentEngine
from banana_english.application.services.prompts import GRAMMAR_ASSESSMENT_VERSION
from banana_english.application.services.structured_llm import StructuredLLM
from banana_english.config.settings import PROJECT_ROOT, Settings
from banana_english.infrastructure.ai.factory import build_llm_provider
from banana_english.infrastructure.content.json_content_repository import JsonContentRepository

SET = PROJECT_ROOT / "content/calibration/grammar_calibration.json"
OUT = PROJECT_ROOT / "docs/calibration"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("BANANA_LLM_PROVIDER", "ollama")
    settings = Settings()
    llm = build_llm_provider(settings)
    content = JsonContentRepository(settings.content_dir)
    engine = LLMGrammarAssessmentEngine(StructuredLLM(llm, cache=None, max_retries=1))
    items = json.loads(SET.read_text())["items"]

    started = time.perf_counter()
    rows = run_calibration(items, content, engine)
    elapsed = time.perf_counter() - started

    OUT.mkdir(parents=True, exist_ok=True)
    baseline_path = OUT / "baseline.json"
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
    baseline_scores = (
        baseline["scores"]
        if baseline and baseline.get("prompt_version") == GRAMMAR_ASSESSMENT_VERSION
        else (baseline["scores"] if baseline else None)
    )
    summary = summarise(rows, baseline_scores)
    labels_verified = sum(1 for i in items if i.get("human_verified"))
    result = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": llm.name,
        "prompt_version": GRAMMAR_ASSESSMENT_VERSION,
        "baseline_prompt_version": baseline.get("prompt_version") if baseline else None,
        "labels_human_verified": labels_verified,
        "seconds": round(elapsed, 1),
        "summary": summary,
        "rows": rows_as_dicts(rows),
    }
    (OUT / "latest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    if args.update_baseline:
        baseline_path.write_text(
            json.dumps(
                {
                    "prompt_version": GRAMMAR_ASSESSMENT_VERSION,
                    "provider": llm.name,
                    "run_at": result["run_at"],
                    "scores": {r.id: r.llm_score for r in rows if r.llm_score is not None},
                },
                indent=2,
            )
            + "\n"
        )
    write_report(result, items)
    print(json.dumps(summary, indent=2))


def write_report(result: dict, items: list[dict]) -> None:
    s = result["summary"]
    notes = {i["id"]: i.get("note", "") for i in items}
    lines = [
        "# Grammar assessment calibration",
        "",
        f"- Run: {result['run_at']} — provider `{result['provider']}`, prompt "
        f"`{result['prompt_version']}`, {result['seconds']} s total",
        f"- Labels verified by a human: **{result['labels_human_verified']}/{s['items']}** "
        "(the rest are AI-drafted rubric labels awaiting teacher review)",
        f"- Graded: {s['graded']}/{s['items']} (failed after retry: {s['failed']})",
        f"- Mean absolute error vs labels: **{s['mean_abs_error']}** points; bias (LLM − label): "
        f"**{s['bias']:+}**",
        f"- Within ±{s['tolerance']} points: **{s['within_tolerance']}/{s['graded']}**; "
        f"is_correct agreement: **{s['is_correct_agreement']}/{s['graded']}**",
    ]
    if "drift" in s:
        d = s["drift"]
        lines.append(
            f"- Drift vs baseline ({d['compared']} items): max {d['max']} points; "
            f"over ±{DRIFT_TOLERANCE}: {d['over_tolerance'] or 'none'}"
        )
    lines += ["", "| id | answer | label | LLM | diff | note |", "|---|---|---|---|---|---|"]
    for r in result["rows"]:
        llm = "—" if r["llm_score"] is None else f"{r['llm_score']:.0f}"
        diff = "—" if r["diff"] is None else f"{r['diff']:+.0f}"
        lines.append(
            f"| {r['id']} | {r['answer']} | {r['label_score']:.0f} | {llm} | {diff} | "
            f"{notes.get(r['id'], '')} |"
        )
    (OUT / "report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
