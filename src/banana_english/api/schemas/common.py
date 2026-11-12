"""Shared HTTP schemas. Scores and mastery use the unified 0-100 rubric scale."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from banana_english.domain.models import (
    Assessor,
    CefrLevel,
    Difficulty,
    ExerciseType,
    MistakeCategory,
    Module,
    RecommendationKind,
)


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(Out):
    code: str = Field(examples=["learner_not_found"])
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(Out):
    error: ErrorBody


class MistakeView(Out):
    category: MistakeCategory
    explanation: str
    fragment: str | None = None
    correction: str | None = None


class AssessmentView(Out):
    score: float = Field(ge=0, le=100)
    is_correct: bool
    band: str = Field(description="Rubric band: excellent | good | minor_error | major_error")
    feedback: str
    mistakes: list[MistakeView]
    corrected_answer: str | None
    assessor: Assessor
    prompt_version: str | None = None
    model: str | None = None


class MasteryChangeView(Out):
    skill_id: str
    before: float
    after: float
    attempt_count: int


class ExerciseView(Out):
    id: str
    module: Module
    skill_id: str
    cefr_level: CefrLevel
    difficulty: Difficulty
    exercise_type: ExerciseType
    instruction: str
    prompt: str
    hint: str | None = None


class ActivityItemView(Out):
    module: Module
    item_id: str
    title: str
    difficulty: Difficulty | None = None


class RecommendationView(Out):
    priority: int
    kind: RecommendationKind
    module: Module
    skill_id: str
    reason_code: str
    reason: str
    evidence: dict[str, Any]
    items: list[ActivityItemView]


class RecommendationsResponse(Out):
    learner_id: str
    generated_at: datetime
    recommendations: list[RecommendationView]


class AttemptResponse(Out):
    attempt_id: str
    item_id: str
    skill_id: str
    submitted_at: datetime
    assessment: AssessmentView
    reference_answers: list[str] = Field(description="Reviewed accepted answers")
    explanation: str | None = Field(default=None, description="Teacher explanation (content)")
    mastery_changes: list[MasteryChangeView]
    next_recommendation: RecommendationView | None


class JobResponse(Out):
    job_id: str
    kind: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
