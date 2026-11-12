"""Module-specific request/response schemas (profile, vocabulary, grammar, listening,
speaking, conversation, tutor, AI Monkey)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from banana_english.api.schemas.common import (
    AssessmentView,
    ExerciseView,
    In,
    MasteryChangeView,
    Out,
    RecommendationView,
)
from banana_english.domain.models import CefrLevel, Difficulty, Module, Role, SrsRating

# --- profile & dashboard ---------------------------------------------------------------


class RegisterRequest(In):
    email: str = Field(min_length=3, max_length=254, examples=["lan@example.com"])
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    current_level: CefrLevel = CefrLevel.A1
    target_level: CefrLevel = CefrLevel.B2
    native_language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")


class LoginRequest(In):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class LearnerProfileResponse(Out):
    learner_id: str
    display_name: str
    current_level: CefrLevel
    target_level: CefrLevel
    native_language: str | None
    created_at: datetime
    total_attempts: int
    correct_attempts: int
    role: Role = Field(
        Role.STUDENT, description="admin | teacher | student (decides which screens to show)"
    )


class AuthResponse(Out):
    token: str = Field(description="Bearer token (the web app uses the httpOnly cookie instead)")
    expires_in_seconds: int
    profile: LearnerProfileResponse


class SkillMasteryView(Out):
    skill_id: str
    module: Module
    skill_name: str
    mastery: float = Field(ge=0, le=100)
    effective_mastery: float = Field(ge=0, le=100, description="After forgetting decay")
    confidence: float = Field(ge=0, le=1)
    attempt_count: int
    correct_count: int
    last_practiced_at: datetime | None
    is_weak: bool
    entry_level: CefrLevel = Field(description="CEFR level at which the skill is introduced")


class MasteryResponse(Out):
    learner_id: str
    weakness_threshold: float
    skills: list[SkillMasteryView]


class WeakSkillView(Out):
    skill_id: str
    skill_name: str
    module: Module
    mastery: float
    effective_mastery: float
    attempt_count: int


class WeakSkillsResponse(Out):
    learner_id: str
    weakness_threshold: float
    skills: list[WeakSkillView]


class MasteryPoint(Out):
    at: datetime
    skill_id: str
    mastery: float
    score: float
    source: str


class MasteryHistoryResponse(Out):
    learner_id: str
    days: int
    points: list[MasteryPoint]


class ActivityDay(Out):
    date: date
    attempts: int


class ActivityResponse(Out):
    learner_id: str
    days: list[ActivityDay]
    active_days: int
    current_streak: int


class RoadmapSkill(Out):
    skill_id: str
    skill_name: str
    module: Module
    effective_mastery: float
    status: Literal["mastered", "in_progress", "not_started"]


class RoadmapLevel(Out):
    level: CefrLevel
    skills: list[RoadmapSkill]
    skills_mastered: int
    words_total: int
    words_started: int
    answers_left: int = Field(description="Answers still needed (estimate, lower bound)")
    weeks_left: int = Field(description="answers_left at the daily goal, in weeks")
    complete: bool


class RoadmapResponse(Out):
    learner_id: str
    current_level: CefrLevel
    target_level: CefrLevel
    daily_goal: int
    mastered_at: float
    levels: list[RoadmapLevel]


class AttemptPart(Out):
    skill_id: str
    score: float


class RecentAttemptView(Out):
    attempt_id: str
    module: Module
    item_id: str
    skill_id: str
    answer: str
    submitted_at: datetime
    status: str
    score: float | None
    is_correct: bool | None
    mistake_count: int
    parts: list[AttemptPart] = Field(
        default_factory=list,
        description="Scores of the skills graded from this one answer (spoken answers: "
        "grammar and fluency); empty when the answer trains a single skill",
    )


# --- vocabulary (SM-2) -----------------------------------------------------------------


class CardBack(Out):
    word: str
    variants: list[str]
    part_of_speech: str
    definition: str
    example: str | None


class CardStateView(Out):
    repetitions: int
    ease_factor: float
    interval_days: int
    due_date: date | None
    lapses: int
    review_count: int


class DueCardView(Out):
    card_id: str
    is_new: bool
    cefr_level: CefrLevel
    front: ExerciseView
    back: CardBack
    state: CardStateView | None


class DueCardsResponse(Out):
    learner_id: str
    cards: list[DueCardView]


class ReviewRequest(In):
    card_id: str = Field(pattern=r"^[A-Za-z0-9.\-]{1,128}$", examples=["apple.noun"])
    rating: SrsRating = Field(description="Again / Hard / Good / Easy -> SM-2 quality 1/3/4/5")
    answer: str | None = Field(
        default=None, max_length=100, description="Optional typed answer; caps the rating if wrong"
    )
    response_time_ms: int | None = Field(default=None, ge=0, le=3_600_000)


class ReviewResponse(Out):
    attempt_id: str
    card_id: str
    rating_applied: SrsRating
    assessment: AssessmentView
    state: CardStateView
    back: CardBack
    mastery_changes: list[MasteryChangeView]
    next_recommendation: RecommendationView | None


# --- grammar ---------------------------------------------------------------------------


class GrammarTopicView(Out):
    skill_id: str
    name: str
    description: str
    exercise_count: int


class GrammarExercisesResponse(Out):
    exercises: list[ExerciseView]


class GrammarAttemptRequest(In):
    exercise_id: str = Field(pattern=r"^gr\.[a-z]+\.\d{3}$", examples=["gr.articles.001"])
    answer: str = Field(max_length=300)
    response_time_ms: int | None = Field(default=None, ge=0, le=3_600_000)


# --- listening -------------------------------------------------------------------------


class ListeningQuestionView(Out):
    id: str
    question: str


class ListeningLessonView(Out):
    id: str
    title: str
    cefr_level: CefrLevel
    difficulty: Difficulty
    duration_seconds: float
    audio_url: str
    questions: list[ListeningQuestionView]


class ListeningLessonsResponse(Out):
    lessons: list[ListeningLessonView]


class TranscriptResponse(Out):
    lesson_id: str
    transcript: str
    answers: dict[str, list[str]]


class ListeningAttemptRequest(In):
    question_id: str = Field(pattern=r"^ls\.[a-z]+\.\d{3}\.q\d$", examples=["ls.train.001.q1"])
    answer: str = Field(max_length=200)
    response_time_ms: int | None = Field(default=None, ge=0, le=3_600_000)


# --- speaking --------------------------------------------------------------------------


class SpeakingPromptView(Out):
    id: str
    title: str
    cefr_level: CefrLevel
    difficulty: Difficulty
    instruction: str
    target_grammar: str | None
    target_grammar_name: str | None = Field(
        description="Display name of target_grammar, e.g. 'Present simple vs present continuous'"
    )
    min_seconds: int
    max_seconds: int


class SpeakingPromptsResponse(Out):
    prompts: list[SpeakingPromptView]


# --- conversation ----------------------------------------------------------------------


class ScenarioView(Out):
    id: str
    title: str
    cefr_level: CefrLevel
    situation: str
    learner_role: str
    goals: list[str]
    max_learner_turns: int


class ScenariosResponse(Out):
    scenarios: list[ScenarioView]


class StartConversationRequest(In):
    scenario_id: str = Field(pattern=r"^cv\.[a-z]+\.\d{3}$")


class MessageRequest(In):
    text: str = Field(min_length=1, max_length=300)


class TurnView(Out):
    role: str
    text: str
    at: datetime


class ConversationView(Out):
    id: str
    scenario: ScenarioView
    status: str
    turns: list[TurnView]
    learner_turns_left: int
    summary: dict | None


# --- tutor -----------------------------------------------------------------------------


class ExplainRequest(In):
    attempt_id: str = Field(min_length=36, max_length=36)
    mistake_index: int = Field(default=0, ge=0, le=10)


class ExplainResponse(Out):
    attempt_id: str
    error_tag: str
    explanation: str
    example: str
    prompt_version: str
    model: str


__all__ = [
    "AssessmentView",
    "MasteryChangeView",
    "RecommendationView",
]


# --- AI Monkey (free chat) -------------------------------------------------------------


class MonkeyMessage(In):
    role: Literal["learner", "monkey"]
    text: str = Field(min_length=1, max_length=1000)


LanguageChoice = Literal["auto", "en", "vi"]


class MonkeyPreferences(In):
    """How AI Monkey teaches: the chat language, the language of explanations and
    corrections (auto = follow the learner), and how much it corrects. Teaching modes are
    presets of the three languages; `custom` is any other combination."""

    mode: Literal["auto", "immersion", "vietnamese_support", "bilingual", "free_chat", "custom"] = (
        "auto"
    )
    conversation_language: LanguageChoice = "auto"
    explanation_language: LanguageChoice = "auto"
    correction_language: LanguageChoice = "auto"
    corrections: Literal["auto", "off", "strict"] = "auto"


class MonkeyChatRequest(In):
    """The conversation so far, oldest first; the last message is the learner's. The server
    keeps no chat history: the client sends it (only the latest turns reach the model).
    `preferences` is optional: the client keeps the ones returned by the previous reply.
    Without it, preferences are rebuilt from the commands in the history ("từ giờ…")."""

    messages: list[MonkeyMessage] = Field(min_length=1, max_length=60)
    preferences: MonkeyPreferences | None = None


class MonkeyPreferencesView(Out):
    mode: str
    conversation_language: str
    explanation_language: str
    correction_language: str
    corrections: str


class MonkeyPolicyView(Out):
    """What this reply actually used (auto resolved)."""

    learner_language: Literal["en", "vi", "mixed"]
    conversation_language: Literal["en", "vi"]
    explanation_language: Literal["en", "vi"]
    correction_language: Literal["en", "vi"]
    corrections: Literal["off", "gentle", "strict"]
    intent: Literal["chat", "explain", "translate", "example", "check"]


class MonkeyChatResponse(Out):
    reply: str
    prompt_version: str
    model: str
    preferences: MonkeyPreferencesView | None = None  # keep and send with the next message
    policy: MonkeyPolicyView | None = None
    changes: list[str] = Field(
        default_factory=list, description='Settings changed by this message, e.g. "Chat: English"'
    )


class MonkeySpeechRequest(In):
    text: str = Field(min_length=1, max_length=600)


class MonkeyTranscriptResponse(Out):
    text: str
    duration_seconds: float


class FeaturesResponse(Out):
    ai_monkey: bool
