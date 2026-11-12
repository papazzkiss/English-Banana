"""Phase 3 regression gate (runs in CI without a model).

scripts/calibrate.py grades the calibration set with the real model and records the result in
docs/calibration/latest.json. This test fails when:
* the grammar prompt version changed but calibration was not re-run for it,
* the recorded run shows a consistent bias of 20+ points (a rubric bug, not noise),
* scores drifted > 10 points vs the accepted baseline on the same answers,
* the calibration set changed since the recorded run.
"""

import json

from banana_english.application.services.calibration import CalibrationRow, summarise
from banana_english.application.services.prompts import GRAMMAR_ASSESSMENT_VERSION
from banana_english.config.settings import PROJECT_ROOT

CAL = PROJECT_ROOT / "docs/calibration"
SET = PROJECT_ROOT / "content/calibration/grammar_calibration.json"


def latest():
    return json.loads((CAL / "latest.json").read_text())


def test_calibration_was_run_for_the_current_prompt_version():
    assert latest()["prompt_version"] == GRAMMAR_ASSESSMENT_VERSION, (
        "grammar prompt changed: run `uv run python scripts/calibrate.py` and review the report"
    )


def test_calibration_covers_the_current_set():
    ids = {i["id"] for i in json.loads(SET.read_text())["items"]}
    assert {r["id"] for r in latest()["rows"]} == ids


def test_no_consistent_bias_and_no_failures():
    s = latest()["summary"]
    assert s["failed"] == 0
    assert abs(s["bias"]) < 20 and s["mean_abs_error"] < 20


def test_no_drift_against_baseline():
    baseline = json.loads((CAL / "baseline.json").read_text())
    assert baseline["prompt_version"] == GRAMMAR_ASSESSMENT_VERSION
    drift = {
        r["id"]: abs(r["llm_score"] - baseline["scores"][r["id"]])
        for r in latest()["rows"]
        if r["llm_score"] is not None
    }
    assert max(drift.values()) <= 10, {k: v for k, v in drift.items() if v > 10}


def test_summary_math():
    rows = [
        CalibrationRow("a", "e", "x", 50, False, 70, True, "llm", ""),
        CalibrationRow("b", "e", "y", 90, True, 60, False, "llm", ""),
        CalibrationRow("c", "e", "z", 30, False, None, None, None, None, "boom"),
    ]
    s = summarise(rows, baseline={"a": 50, "b": 60})
    assert (s["graded"], s["failed"], s["mean_abs_error"], s["bias"]) == (2, 1, 25, -5)
    assert s["within_tolerance"] == 0 and s["is_correct_agreement"] == 0
    assert s["drift"]["over_tolerance"] == ["a"]
