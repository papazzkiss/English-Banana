"""Benchmark dataset: dataset.json, with each category's shared checks merged into its tests."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from banana_english.benchmark.scoring import DIMENSIONS

DATASET_PATH = Path(__file__).with_name("dataset.json")
CATEGORIES = (
    "grammar_correction",
    "grammar_explanation",
    "conversation",
    "vocabulary",
    "complex",
    "voice",
)
SUITES = ("quick", "full")


def load_dataset(path: Path = DATASET_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    shared = data["category_checks"]
    tests = []
    for test in data["tests"]:
        merged = dict(test)
        merged["checks"] = [*shared.get(test["category"], []), *test.get("checks", [])]
        tests.append(merged)
    return {"version": data["version"], "notes": data.get("notes", ""), "tests": tests}


def select(tests: list[dict], suite: str) -> list[dict]:
    if suite == "full":
        return tests
    if suite == "quick":
        return [t for t in tests if t.get("quick")]
    raise ValueError(f"unknown suite {suite!r}; choose one of {SUITES}")


def validate(tests: list[dict]) -> list[str]:
    """Problems with the dataset (empty list = valid)."""
    problems = []
    ids = Counter(t["id"] for t in tests)
    problems += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    for t in tests:
        if t["category"] not in CATEGORIES:
            problems.append(f"{t['id']}: unknown category {t['category']}")
        if not t["checks"]:
            problems.append(f"{t['id']}: no checks")
        for c in t["checks"]:
            if c.get("dim") not in DIMENSIONS:
                problems.append(
                    f"{t['id']}: check {c.get('type')} has unknown dimension {c.get('dim')}"
                )
    return problems
