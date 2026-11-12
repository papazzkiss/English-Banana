"""Phase 3 calibration: compare LLM grades with labelled answers, and with the previous run.

* agreement: |llm - label| per item, mean absolute error, bias (mean llm - label),
  is_correct agreement, share of items within 20 points.
  A consistent bias of 20+ points is a rubric bug: fix the prompt, do not accept it.
* drift (regression): |llm_now - llm_baseline| per item; > 10 points on the same answer after a
  prompt change is a warning, not noise.

Calibration always bypasses the verdict cache — a cache would hide drift.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any

from banana_english.application.services.grammar_assessment import LLMGrammarAssessmentEngine
from banana_english.domain.interfaces.assessment import AssessmentUnavailableError
from banana_english.domain.interfaces.repositories import ContentRepository

AGREEMENT_TOLERANCE = 20
DRIFT_TOLERANCE = 10


@dataclass(frozen=True)
class CalibrationRow:
    id: str
    exercise_id: str
    answer: str
    label_score: float
    label_is_correct: bool
    llm_score: float | None
    llm_is_correct: bool | None
    assessor: str | None
    feedback: str | None
    error: str | None = None

    @property
    def diff(self) -> float | None:
        return None if self.llm_score is None else self.llm_score - self.label_score


def run_calibration(
    items: list[dict[str, Any]], content: ContentRepository, engine: LLMGrammarAssessmentEngine
) -> list[CalibrationRow]:
    rows = []
    for item in items:
        exercise = content.get_exercise(item["exercise_id"])
        if exercise is None:
            raise ValueError(f"unknown exercise {item['exercise_id']} in calibration set")
        try:
            a = engine.assess(exercise, item["answer"])
            rows.append(
                CalibrationRow(
                    item["id"],
                    exercise.id,
                    item["answer"],
                    item["label_score"],
                    item["label_is_correct"],
                    a.score,
                    a.is_correct,
                    a.assessor.value,
                    a.feedback,
                )
            )
        except AssessmentUnavailableError as exc:
            rows.append(
                CalibrationRow(
                    item["id"],
                    exercise.id,
                    item["answer"],
                    item["label_score"],
                    item["label_is_correct"],
                    None,
                    None,
                    None,
                    None,
                    exc.reason,
                )
            )
    return rows


def summarise(
    rows: list[CalibrationRow], baseline: dict[str, float] | None = None
) -> dict[str, Any]:
    graded = [r for r in rows if r.llm_score is not None]
    diffs = [r.diff for r in graded]
    summary: dict[str, Any] = {
        "items": len(rows),
        "graded": len(graded),
        "failed": len(rows) - len(graded),
        "mean_abs_error": round(mean(abs(d) for d in diffs), 2) if diffs else None,
        "bias": round(mean(diffs), 2) if diffs else None,
        "within_tolerance": sum(1 for d in diffs if abs(d) < AGREEMENT_TOLERANCE),
        "is_correct_agreement": sum(1 for r in graded if r.llm_is_correct == r.label_is_correct),
        "tolerance": AGREEMENT_TOLERANCE,
    }
    if baseline:
        drift = {r.id: abs(r.llm_score - baseline[r.id]) for r in graded if r.id in baseline}
        summary["drift"] = {
            "compared": len(drift),
            "max": round(max(drift.values()), 2) if drift else 0.0,
            "over_tolerance": sorted(k for k, v in drift.items() if v > DRIFT_TOLERANCE),
            "tolerance": DRIFT_TOLERANCE,
        }
    return summary


def rows_as_dicts(rows: list[CalibrationRow]) -> list[dict[str, Any]]:
    return [{**asdict(r), "diff": r.diff} for r in rows]
