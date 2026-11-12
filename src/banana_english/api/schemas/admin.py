"""Administration, teacher and question-review API models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from banana_english.api.schemas.common import In, Out
from banana_english.api.schemas.modules import (
    ActivityResponse,
    MasteryResponse,
    WeakSkillsResponse,
)
from banana_english.domain.models import CefrLevel, Difficulty, Module, Role
from banana_english.domain.models.bank import BankStatus, QuestionType


class UserView(Out):
    user_id: str
    display_name: str
    email: str | None
    role: Role
    is_active: bool
    created_at: datetime
    attempts: int = Field(description="Assessed attempts")
    correct: int
    last_active: datetime | None


class UsersResponse(Out):
    total: int
    users: list[UserView]


class UserDetailView(UserView):
    teacher_ids: list[str] = Field(description="Teachers following this user")
    student_ids: list[str] = Field(description="Students this teacher follows")


class UserUpdateRequest(In):
    """Only these two fields can change; anything else is rejected (422)."""

    role: Role | None = None
    is_active: bool | None = None


class AdminStatsResponse(Out):
    users: dict[str, dict[str, int]] = Field(description="Per role: active / inactive")
    new_users_7d: int
    attempts: dict[str, int]
    bank: dict[str, dict[str, int]] = Field(description="Questions per skill and status")
    bank_last_import: dict[str, Any] | None
    system: dict[str, Any] = Field(description="Read-only configuration summary")


class StudentProgressResponse(Out):
    student: UserView
    mastery: MasteryResponse
    weak_skills: WeakSkillsResponse
    activity: ActivityResponse


class ReviewOptionView(Out):
    id: str
    text: str


class ReviewQuestionView(Out):
    """A question with its answer: for reviewers only, never sent to learners."""

    id: str
    skill: Module
    skill_id: str
    level: CefrLevel
    topic: str
    point: str
    difficulty: Difficulty
    qtype: QuestionType
    status: BankStatus
    quality: float
    instruction: str
    prompt: str
    options: list[ReviewOptionView]
    display: dict[str, Any]
    answer: dict[str, Any]
    explanation: str
    explanation_vi: str
    passage_id: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None


class ReviewPageResponse(Out):
    total: int
    questions: list[ReviewQuestionView]


class ReviewStatusRequest(In):
    status: BankStatus = Field(description="approved | validated | disabled")
