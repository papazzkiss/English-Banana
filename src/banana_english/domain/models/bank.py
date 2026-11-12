"""Question bank: a large pool of practice questions with fixed answers (grammar, vocabulary,
reading, listening). Sets are drawn from the pool on demand, so the same pool yields a
different set every time, and every answer is checked by rules (no LLM on the answer path).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from banana_english.domain.models.enums import CefrLevel, Difficulty, Module


class QuestionType(StrEnum):
    MCQ = "mcq"  # one option is correct
    TRUE_FALSE = "true_false"  # options "true" / "false"
    ERROR_ID = "error_id"  # which underlined part is wrong (options are the parts)
    FILL_BLANK = "fill_blank"  # typed answer, a list of accepted answers
    DICTATION = "dictation"  # typed sentence, word-level comparison
    ORDERING = "ordering"  # put the given pieces in order
    MATCHING = "matching"  # pair every left item with a right item


class BankStatus(StrEnum):
    DRAFT = "draft"  # generated, failed a check or scored too low: never served
    VALIDATED = "validated"  # passed every automatic check: served
    APPROVED = "approved"  # also checked by a person: served first
    DISABLED = "disabled"  # withdrawn


SERVED_STATUSES = (BankStatus.VALIDATED, BankStatus.APPROVED)
BANK_MODULES = (Module.GRAMMAR, Module.VOCABULARY, Module.READING, Module.LISTENING)


@dataclass(frozen=True)
class BankOption:
    id: str
    text: str


@dataclass(frozen=True)
class BankPassage:
    """A reading text or a listening recording (its transcript), shared by several questions."""

    id: str
    skill: Module
    level: CefrLevel
    topic: str
    title: str
    text: str
    audio: str | None = None  # path under the bank's audio directory
    duration_s: float | None = None
    source: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BankQuestion:
    id: str
    skill: Module
    skill_id: str  # the mastery skill it trains (e.g. grammar.present_perfect)
    level: CefrLevel
    topic: str
    point: str  # grammar point, vocabulary focus or reading/listening question focus
    difficulty: Difficulty
    qtype: QuestionType
    prompt: str
    instruction: str
    answer: Mapping[str, Any]  # never sent to the client before it answers
    explanation: str
    explanation_vi: str = ""
    options: tuple[BankOption, ...] = ()
    passage_id: str | None = None
    tags: tuple[str, ...] = ()
    quality: float = 0.0
    status: BankStatus = BankStatus.VALIDATED
    # what the client needs to show some types: {"pieces": [...]} (ordering, already shuffled),
    # {"left": [{"id", "text"}]} (matching); never the answer
    display: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QuestionFilter:
    skill: Module
    levels: tuple[CefrLevel, ...] = ()
    topics: tuple[str, ...] = ()
    points: tuple[str, ...] = ()
    qtypes: tuple[QuestionType, ...] = ()
    difficulties: tuple[Difficulty, ...] = ()
    skill_ids: tuple[str, ...] = ()  # mastery skills (e.g. the learner's weak ones)
    statuses: tuple[BankStatus, ...] = SERVED_STATUSES


@dataclass(frozen=True)
class QuestionStat:
    """One learner's history with one question (drives anti-repetition and review)."""

    learner_id: str
    question_id: str
    attempts: int
    correct: int
    wrong: int
    last_seen: datetime
    last_correct: bool


@dataclass(frozen=True)
class CheckResult:
    correct: bool
    score: float  # 0-100 (partial credit for dictation and matching)
    correct_answer: str  # what to show the learner
    detail: Mapping[str, Any] = field(default_factory=dict)
