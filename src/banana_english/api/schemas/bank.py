"""Question bank API models. Questions go out WITHOUT their answers; the answer comes back
only in the check result."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from banana_english.api.schemas.common import In, MasteryChangeView, Out
from banana_english.domain.models import CefrLevel, Difficulty
from banana_english.domain.models.bank import QuestionType

BankSkill = Literal["grammar", "vocabulary", "reading", "listening"]


class BankFacetsResponse(Out):
    skill: BankSkill
    total: int
    levels: dict[str, int]
    topics: dict[str, int]
    points: dict[str, int]
    qtypes: dict[str, int]
    difficulties: dict[str, int]
    point_names: dict[str, str] = Field(
        default_factory=dict, description="Display name of each grammar point"
    )


class BankSetRequest(In):
    levels: list[CefrLevel] = Field(default_factory=list, max_length=6)
    topics: list[str] = Field(default_factory=list, max_length=30)
    points: list[str] = Field(default_factory=list, max_length=30)
    qtypes: list[QuestionType] = Field(default_factory=list, max_length=7)
    difficulties: list[Difficulty] = Field(default_factory=list, max_length=3)
    count: int = Field(10, ge=1, le=50)


class BankOptionView(Out):
    id: str
    text: str


class BankQuestionView(Out):
    id: str
    qtype: QuestionType
    level: CefrLevel
    topic: str
    point: str
    difficulty: Difficulty
    instruction: str
    prompt: str
    options: list[BankOptionView]
    passage_id: str | None = None
    pieces: list[str] | None = Field(None, description="ordering: the pieces, shuffled")
    left: list[BankOptionView] | None = Field(None, description="matching: left column")


class BankPassageView(Out):
    id: str
    level: CefrLevel
    topic: str
    title: str
    text: str | None = Field(
        None,
        description="reading text; null for listening (transcript "
        "via /bank/passages/{id}/transcript after answering)",
    )
    audio_url: str | None = None
    duration_s: float | None = None
    source: dict[str, Any] = Field(default_factory=dict)


class BankSetResponse(Out):
    skill: BankSkill
    questions: list[BankQuestionView]
    passages: list[BankPassageView]
    review_count: int


class BankAnswerRequest(In):
    question_id: str = Field(min_length=1, max_length=64)
    answer: str | list[str] | dict[str, str] = Field(
        description="option id (mcq, true_false, error_id), text (fill_blank, dictation), "
        "list of pieces (ordering), {left id: right id} (matching)"
    )
    response_time_ms: int | None = Field(None, ge=0, le=3_600_000)


class BankAnswerResponse(Out):
    attempt_id: str
    question_id: str
    correct: bool
    score: float
    correct_answer: str
    explanation: str
    explanation_vi: str
    detail: dict[str, Any]
    mastery: MasteryChangeView


class BankTranscriptResponse(Out):
    passage_id: str
    title: str
    transcript: str


class BankSummaryResponse(Out):
    skill: BankSkill
    pool_size: int
    questions_seen: int
    correct_answers: int
    wrong_answers: int
    to_review: int
