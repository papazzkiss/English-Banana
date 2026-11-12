"""Instant, deterministic answer checking for bank questions: the answer path never calls an
LLM. Pure functions, microseconds per check.

Answer specs (the `answer` field of a question):
  mcq / true_false / error_id  {"option": "b"}
  fill_blank                   {"accepted": ["has lived", "'s lived"]}
  dictation                    {"text": "I have two brothers."}
  ordering                     {"order": ["She", "has", "lived", "here"]}  (the right sequence)
  matching                     {"pairs": {"l1": "r3", "l2": "r1", ...}}
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from banana_english.domain.models.bank import BankQuestion, CheckResult, QuestionType
from banana_english.domain.services.answer_matching import matches_any, normalize_answer

_WORD = re.compile(r"[a-z0-9']+")
DICTATION_PASS = 0.9  # share of words right to count the sentence as correct


class InvalidAnswerError(ValueError):
    """The submitted answer has the wrong shape for the question type."""


def _option_text(question: BankQuestion, option_id: str) -> str:
    return next((o.text for o in question.options if o.id == option_id), option_id)


def _words(text: str) -> list[str]:
    return _WORD.findall(normalize_answer(text).replace("’", "'"))


def _word_accuracy(expected: Sequence[str], got: Sequence[str]) -> float:
    """1 - word edit distance / expected length (0..1)."""
    if not expected:
        return 1.0 if not got else 0.0
    previous = list(range(len(got) + 1))
    for i, e in enumerate(expected, start=1):
        current = [i]
        for j, g in enumerate(got, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (e != g)))
        previous = current
    return max(0.0, 1.0 - previous[-1] / len(expected))


def check_answer(question: BankQuestion, answer: Any) -> CheckResult:
    spec: Mapping[str, Any] = question.answer
    qtype = question.qtype

    if qtype in (QuestionType.MCQ, QuestionType.TRUE_FALSE, QuestionType.ERROR_ID):
        if not isinstance(answer, str):
            raise InvalidAnswerError("expected an option id")
        right = str(spec["option"])
        ok = answer == right
        return CheckResult(
            ok,
            100.0 if ok else 0.0,
            _option_text(question, right),
            {"chosen": answer, "right_option": right},
        )

    if qtype is QuestionType.FILL_BLANK:
        if not isinstance(answer, str):
            raise InvalidAnswerError("expected text")
        accepted = list(spec["accepted"])
        ok = matches_any(answer, accepted)
        return CheckResult(ok, 100.0 if ok else 0.0, accepted[0])

    if qtype is QuestionType.DICTATION:
        if not isinstance(answer, str):
            raise InvalidAnswerError("expected text")
        expected = _words(spec["text"])
        accuracy = _word_accuracy(expected, _words(answer))
        return CheckResult(
            accuracy >= DICTATION_PASS,
            round(100 * accuracy, 1),
            spec["text"],
            {"word_accuracy": round(accuracy, 3)},
        )

    if qtype is QuestionType.ORDERING:
        if not isinstance(answer, list) or not all(isinstance(x, str) for x in answer):
            raise InvalidAnswerError("expected a list of pieces")
        right = [str(x) for x in spec["order"]]
        ok = [normalize_answer(x) for x in answer] == [normalize_answer(x) for x in right]
        return CheckResult(ok, 100.0 if ok else 0.0, " ".join(right))

    if qtype is QuestionType.MATCHING:
        if not isinstance(answer, dict):
            raise InvalidAnswerError("expected pairs")
        pairs: Mapping[str, str] = spec["pairs"]
        right = sum(1 for left, target in pairs.items() if answer.get(left) == target)
        score = 100.0 * right / len(pairs) if pairs else 0.0
        return CheckResult(
            right == len(pairs),
            round(score, 1),
            "",
            {"right_pairs": dict(pairs), "correct_count": right},
        )

    raise InvalidAnswerError(f"unknown question type {qtype}")
