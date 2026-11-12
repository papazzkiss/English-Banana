"""Core domain entities and value objects.

Plain dataclasses on purpose: the domain must not depend on FastAPI, Pydantic,
SQLAlchemy or any model SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from banana_english.domain.models.enums import (
    Assessor,
    AttemptStatus,
    CefrLevel,
    ContentReviewStatus,
    ConversationStatus,
    Difficulty,
    ExerciseType,
    JobStatus,
    MistakeCategory,
    Module,
    RecommendationKind,
    Role,
)

# --- Learner -------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    id: str
    display_name: str
    created_at: datetime
    role: Role = Role.STUDENT
    is_active: bool = True


@dataclass(frozen=True)
class UserSummary:
    """A user as an admin or a teacher sees it in a list: account and learning totals."""

    user: User
    email: str | None  # None for a user created before accounts existed
    attempts: int
    correct: int
    last_active: datetime | None


@dataclass(frozen=True)
class Principal:
    """The signed-in user as the server knows it (from the session, never from the request)."""

    user_id: str
    role: Role


@dataclass(frozen=True)
class Account:
    user_id: str
    email: str  # normalised: lower-case, trimmed
    password_hash: str
    created_at: datetime


@dataclass(frozen=True)
class AuthSession:
    token_hash: str  # SHA-256 of the bearer token; the token itself is never stored
    user_id: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class LearnerProfile:
    user_id: str
    current_level: CefrLevel
    target_level: CefrLevel
    native_language: str | None
    created_at: datetime


# --- Skills & mastery -----------------------------------------------------------


@dataclass(frozen=True)
class Skill:
    id: str  # skill tag, e.g. "grammar.articles", "vocabulary.a1", "listening.comprehension"
    module: Module
    name: str
    description: str
    entry_level: CefrLevel  # lowest CEFR level of the skill's content


@dataclass(frozen=True)
class SkillMastery:
    """Learner state for one skill tag. Scale 0-100. Produced only by domain.services.mastery."""

    learner_id: str
    skill_id: str
    mastery: float
    confidence: float  # share of the EMA weight that comes from real attempts (0..1)
    attempt_count: int
    correct_count: int
    last_practiced_at: datetime | None


@dataclass(frozen=True)
class MasteryEvent:
    """One mastery change (the attempt_log). Source of mastery history charts."""

    learner_id: str
    skill_id: str
    score: float
    mastery_before: float
    mastery_after: float
    at: datetime
    attempt_id: str | None = None
    source: str = "attempt"


# --- Content --------------------------------------------------------------------


@dataclass(frozen=True)
class VocabularyItem:
    id: str  # e.g. "abandon.verb"
    word: str
    variants: tuple[str, ...]
    part_of_speech: str
    cefr_level: CefrLevel
    definition: str
    example: str | None
    review_status: ContentReviewStatus

    @property
    def skill_id(self) -> str:
        return f"vocabulary.{self.cefr_level.value.lower()}"


@dataclass(frozen=True)
class Exercise:
    """Anything a learner answers in text: grammar exercise, vocabulary card, listening question."""

    id: str
    module: Module
    skill_id: str
    cefr_level: CefrLevel
    exercise_type: ExerciseType
    instruction: str
    prompt: str
    accepted_answers: tuple[str, ...]
    review_status: ContentReviewStatus
    difficulty: Difficulty = Difficulty.MEDIUM
    explanation: str | None = None
    hint: str | None = None
    item_id: str | None = None  # vocabulary item or listening lesson id


@dataclass(frozen=True)
class ListeningQuestion:
    id: str
    question: str
    accepted_answers: tuple[str, ...]


@dataclass(frozen=True)
class ListeningLesson:
    id: str
    title: str
    cefr_level: CefrLevel
    difficulty: Difficulty
    transcript: str
    audio_file: str  # relative to content/listening/audio
    duration_seconds: float
    questions: tuple[ListeningQuestion, ...]
    review_status: ContentReviewStatus


@dataclass(frozen=True)
class SpeakingPrompt:
    id: str
    title: str
    cefr_level: CefrLevel
    difficulty: Difficulty
    instruction: str
    target_grammar: str | None  # grammar skill tag the prompt is designed to elicit
    min_seconds: int
    max_seconds: int
    review_status: ContentReviewStatus


@dataclass(frozen=True)
class ConversationScenario:
    id: str
    title: str
    cefr_level: CefrLevel
    assistant_role: str
    learner_role: str
    situation: str
    opening_line: str
    goals: tuple[str, ...]
    target_skills: tuple[str, ...]
    max_learner_turns: int
    review_status: ContentReviewStatus


# --- Learning loop --------------------------------------------------------------


@dataclass(frozen=True)
class Mistake:
    category: MistakeCategory
    explanation: str
    fragment: str | None = None
    correction: str | None = None


@dataclass(frozen=True)
class Assessment:
    """Validated result of assessing one answer (0-100). The only input to mastery updates."""

    score: float
    is_correct: bool
    feedback: str
    assessor: Assessor
    mistakes: tuple[Mistake, ...] = ()
    corrected_answer: str | None = None
    prompt_version: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 100.0:
            raise ValueError(f"score must be within [0, 100], got {self.score}")


@dataclass(frozen=True)
class Attempt:
    id: str
    learner_id: str
    module: Module
    item_id: str  # exercise / card / listening question / speaking prompt / conversation turn
    skill_id: str
    answer: str
    submitted_at: datetime
    status: AttemptStatus
    response_time_ms: int | None = None
    assessment: Assessment | None = None
    details: dict[str, Any] = field(default_factory=dict)  # e.g. transcript, fluency metrics


@dataclass(frozen=True)
class VocabularyCard:
    """SM-2 state for one learner x vocabulary item."""

    learner_id: str
    item_id: str
    repetitions: int = 0
    ease_factor: float = 2.5
    interval_days: int = 0
    due_date: date | None = None
    last_reviewed_at: datetime | None = None
    lapses: int = 0
    review_count: int = 0
    created_at: datetime | None = None


@dataclass(frozen=True)
class ConversationTurn:
    role: str  # "assistant" | "learner"
    text: str
    at: datetime


@dataclass(frozen=True)
class Conversation:
    id: str
    learner_id: str
    scenario_id: str
    status: ConversationStatus
    turns: tuple[ConversationTurn, ...]
    created_at: datetime
    summary: dict[str, Any] | None = None

    @property
    def learner_turns(self) -> list[ConversationTurn]:
        return [t for t in self.turns if t.role == "learner"]


@dataclass(frozen=True)
class Job:
    id: str
    learner_id: str
    kind: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class ActivityItem:
    """One concrete thing to do next."""

    module: Module
    item_id: str  # exercise id, card id, lesson id, prompt id or scenario id
    title: str
    difficulty: Difficulty | None = None


@dataclass(frozen=True)
class Recommendation:
    kind: RecommendationKind
    module: Module
    skill_id: str
    items: tuple[ActivityItem, ...]
    priority: int
    reason_code: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
