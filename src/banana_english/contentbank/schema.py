"""The question bank's record format (content/bank/*.jsonl.gz), shared by the generators, the
validator, the importer and the audit. One JSON object per line: a question or a passage.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from banana_english.domain.models import CefrLevel, Difficulty
from banana_english.domain.models.bank import BankStatus, QuestionType
from banana_english.domain.services.answer_matching import normalize_answer

Skill = Literal["grammar", "vocabulary", "reading", "listening"]
BANK_LEVELS = (CefrLevel.A1, CefrLevel.A2, CefrLevel.B1, CefrLevel.B2, CefrLevel.C1)
BLANK = "___"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRef(_Strict):
    id: str  # a sources.py id, or "template:<name>" for texts written from templates
    ref: str = ""  # sentence id / article title
    license: str


class OptionRecord(_Strict):
    id: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1, max_length=400)


class PassageRecord(_Strict):
    kind: Literal["passage"] = "passage"
    id: str = Field(pattern=r"^(rd|ls)\.[a-z0-9._-]+$", max_length=64)
    skill: Literal["reading", "listening"]
    level: CefrLevel
    topic: str = Field(max_length=32)
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=20, max_length=6000)
    audio: str | None = None
    duration_s: float | None = None
    source: SourceRef
    status: BankStatus = BankStatus.VALIDATED
    quality: float = Field(ge=0, le=1)


class QuestionRecord(_Strict):
    kind: Literal["question"] = "question"
    id: str = Field(pattern=r"^(gr|vo|rd|ls)\.[a-z0-9._-]+$", max_length=64)
    skill: Skill
    skill_id: str = Field(max_length=64)
    level: CefrLevel
    topic: str = Field(max_length=32)
    point: str = Field(max_length=48)
    difficulty: Difficulty
    qtype: QuestionType
    instruction: str = Field(max_length=300)
    prompt: str = Field(min_length=1, max_length=1500)
    options: list[OptionRecord] = Field(default_factory=list, max_length=8)
    answer: dict[str, Any]
    explanation: str = Field(min_length=10, max_length=1200)
    explanation_vi: str = Field(default="", max_length=1500)
    passage_id: str | None = None
    display: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=12)
    source: SourceRef
    status: BankStatus = BankStatus.VALIDATED
    quality: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _consistent(self) -> QuestionRecord:
        problems = question_problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self.model_dump(mode="json", exclude={"status", "quality"}))


def content_hash(data: dict[str, Any]) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode()).hexdigest()


def question_problems(q: QuestionRecord) -> list[str]:
    """Structural checks every question must pass (the generators' own checks come on top)."""
    problems: list[str] = []
    ids = [o.id for o in q.options]
    texts = [normalize_answer(o.text) for o in q.options]
    choice = q.qtype in (QuestionType.MCQ, QuestionType.TRUE_FALSE, QuestionType.ERROR_ID)
    if choice:
        if len(q.options) < 2:
            problems.append("needs at least 2 options")
        if len(set(ids)) != len(ids):
            problems.append("duplicate option ids")
        if len(set(texts)) != len(texts):
            problems.append("duplicate option texts")
        if q.answer.get("option") not in ids:
            problems.append("answer is not one of the options")
        if q.qtype is QuestionType.TRUE_FALSE and sorted(texts) != ["false", "true"]:
            problems.append("true/false options must be True and False")
    elif q.qtype is QuestionType.FILL_BLANK:
        accepted = q.answer.get("accepted")
        if not accepted or not all(isinstance(a, str) and a.strip() for a in accepted):
            problems.append("fill_blank needs accepted answers")
        if q.prompt.count(BLANK) != 1:
            problems.append("fill_blank prompt needs exactly one blank")
    elif q.qtype is QuestionType.DICTATION:
        if not isinstance(q.answer.get("text"), str) or len(q.answer["text"]) < 3:
            problems.append("dictation needs the text")
        if q.passage_id is None:
            problems.append("dictation needs its recording")
    elif q.qtype is QuestionType.ORDERING:
        order = q.answer.get("order")
        pieces = q.display.get("pieces")
        if not order or sorted(order) != sorted(pieces or []):
            problems.append("ordering pieces must be the answer's pieces")
        if pieces == order:
            problems.append("ordering pieces are not shuffled")
    elif q.qtype is QuestionType.MATCHING:
        pairs = q.answer.get("pairs") or {}
        left = [x["id"] for x in q.display.get("left") or []]
        if sorted(pairs) != sorted(left) or len(left) < 3:
            problems.append("matching needs 3+ left items, all paired")
        if not set(pairs.values()) <= set(ids) or len(set(pairs.values())) != len(pairs):
            problems.append("matching targets must be distinct options")
    if choice and q.prompt.count(BLANK) > 1:
        problems.append("more than one blank")
    if q.skill in ("reading", "listening") and q.passage_id is None:
        problems.append(f"{q.skill} questions need a passage")
    if re.search(r"\s{2,}", q.prompt.replace("\n", " ")):
        problems.append("repeated whitespace in prompt")
    return problems


def parse_record(line: str) -> QuestionRecord | PassageRecord:
    data = json.loads(line)
    if data.get("kind") == "passage":
        return PassageRecord.model_validate(data)
    return QuestionRecord.model_validate(data)


__all__ = [
    "BANK_LEVELS",
    "BLANK",
    "OptionRecord",
    "PassageRecord",
    "QuestionRecord",
    "SourceRef",
    "ValidationError",
    "content_hash",
    "parse_record",
    "question_problems",
]
