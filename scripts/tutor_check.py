"""Phase 9 check: run the AI Tutor on real errors from the calibration set and write the
explanations to docs/calibration/tutor_check.md for a teacher to verify (a vague or wrong
grammar explanation is worse than none).

    uv run python scripts/tutor_check.py [--limit 10]
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime

from banana_english.application.services.grammar_assessment import LLMGrammarAssessmentEngine
from banana_english.application.services.prompts import (
    GRAMMAR_ASSESSMENT_VERSION,
    TUTOR_EXPLAIN_VERSION,
)
from banana_english.application.services.structured_llm import StructuredLLM
from banana_english.application.services.tutor import Tutor
from banana_english.config.settings import PROJECT_ROOT, Settings
from banana_english.domain.interfaces.assessment import AssessmentUnavailableError
from banana_english.infrastructure.ai.factory import build_llm_provider
from banana_english.infrastructure.content.json_content_repository import JsonContentRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    os.environ.setdefault("BANANA_LLM_PROVIDER", "ollama")
    settings = Settings()
    llm = build_llm_provider(settings)
    content = JsonContentRepository(settings.content_dir)
    structured = StructuredLLM(llm, cache=None)
    grader, tutor = LLMGrammarAssessmentEngine(structured), Tutor(structured)
    items = json.loads((PROJECT_ROOT / "content/calibration/grammar_calibration.json").read_text())[
        "items"
    ]

    lines = [
        "# AI Tutor check (Phase 9)",
        "",
        f"- Run: {datetime.now(UTC).isoformat(timespec='seconds')} — `{llm.name}`, grading "
        f"`{GRAMMAR_ASSESSMENT_VERSION}`, tutor `{TUTOR_EXPLAIN_VERSION}`",
        "- Teacher verdict column: fill in ✅ correct & clear / ⚠️ vague / ❌ wrong.",
        "- The tutor is grounded in the exercise's teacher-written rule (tutor_explain_v2).",
        "",
        "| # | learner answer | error tag | tutor explanation | tutor example | teacher |",
        "|---|---|---|---|---|---|",
    ]
    done = 0
    for item in (i for i in items if not i["label_is_correct"]):
        if done >= args.limit:
            break
        exercise = content.get_exercise(item["exercise_id"])
        try:
            assessment = grader.assess(exercise, item["answer"])
            if not assessment.mistakes:
                lines.append(
                    f"| {done + 1} | {item['answer']} | (grader found no error) | — | — | |"
                )
                done += 1
                continue
            e = tutor.explain(
                assessment.mistakes[0],
                item["answer"],
                exercise.accepted_answers[0],
                exercise.cefr_level.value,
                teacher_rule=exercise.explanation,
                task=f"{exercise.instruction} {exercise.prompt}",
            )
            lines.append(
                f"| {done + 1} | {item['answer']} | {e.error_tag} | "
                f"{e.explanation.replace('|', '/')} | {e.example} | |"
            )
        except AssessmentUnavailableError as exc:
            lines.append(
                f"| {done + 1} | {item['answer']} | (failed: {exc.reason[:60]}) | — | — | |"
            )
        done += 1
        print(f"{done}/{args.limit}", flush=True)
    out = PROJECT_ROOT / "docs/calibration/tutor_check.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
