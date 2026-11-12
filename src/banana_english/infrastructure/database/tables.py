"""Relational schema (PostgreSQL in production, SQLite in tests)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UTCDateTime(TypeDecorator[datetime]):
    """Store UTC, always return timezone-aware datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # access control (revision 0004): existing users became active students
    role: Mapped[str] = mapped_column(String(16), server_default="student", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())


class TeacherStudentRow(Base):
    """Which students a teacher may follow (set by an admin)."""

    __tablename__ = "teacher_students"

    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AccountRow(Base):
    __tablename__ = "accounts"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class SessionRow(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class LearnerProfileRow(Base):
    __tablename__ = "learner_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    current_level: Mapped[str] = mapped_column(String(2))
    target_level: Mapped[str] = mapped_column(String(2))
    native_language: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class SkillMasteryRow(Base):
    __tablename__ = "skill_mastery"

    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mastery: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    attempt_count: Mapped[int] = mapped_column(Integer)
    correct_count: Mapped[int] = mapped_column(Integer)
    last_practiced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class MasteryEventRow(Base):
    """attempt_log: one row per mastery change — the source of mastery-history charts."""

    __tablename__ = "mastery_events"
    __table_args__ = (Index("ix_mastery_events_learner_time", "learner_id", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    skill_id: Mapped[str] = mapped_column(String(64))
    attempt_id: Mapped[str | None] = mapped_column(String(36))
    source: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float)
    mastery_before: Mapped[float] = mapped_column(Float)
    mastery_after: Mapped[float] = mapped_column(Float)
    at: Mapped[datetime] = mapped_column(UTCDateTime)


class AttemptRow(Base):
    __tablename__ = "attempts"
    __table_args__ = (Index("ix_attempts_learner_time", "learner_id", "submitted_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    module: Mapped[str] = mapped_column(String(16))
    item_id: Mapped[str] = mapped_column(String(128))
    skill_id: Mapped[str] = mapped_column(String(64))
    answer: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(32))
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    # assessment (1:1, NULL when status = assessment_failed)
    score: Mapped[float | None] = mapped_column(Float)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    feedback: Mapped[str | None] = mapped_column(Text)
    assessor: Mapped[str | None] = mapped_column(String(32))
    corrected_answer: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    mistakes: Mapped[list[MistakeRow]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan", order_by="MistakeRow.id"
    )


class MistakeRow(Base):
    __tablename__ = "mistakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"))
    category: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(Text)
    fragment: Mapped[str | None] = mapped_column(Text)
    correction: Mapped[str | None] = mapped_column(Text)

    attempt: Mapped[AttemptRow] = relationship(back_populates="mistakes")


class VocabularyCardRow(Base):
    __tablename__ = "vocabulary_cards"
    __table_args__ = (Index("ix_cards_due", "learner_id", "due_date"),)

    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    repetitions: Mapped[int] = mapped_column(Integer)
    ease_factor: Mapped[float] = mapped_column(Float)
    interval_days: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    lapses: Mapped[int] = mapped_column(Integer)
    review_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    scenario_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    turns: Mapped[list[Any]] = mapped_column(JSON)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class LLMCallRow(Base):
    """Audit log: trace any score back to the exact prompt version + raw provider response."""

    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_request", "request_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    task: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    latency_ms: Mapped[float] = mapped_column(Float)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


# --- Question bank (grammar / vocabulary / reading / listening) -----------------------------
# Imported from content/bank by `python -m banana_english.contentbank import`. Questions carry
# an indexed random key (`rand`): a set is drawn with "rand >= r ORDER BY rand LIMIT k" under
# the filter indexes, never ORDER BY RANDOM() over the whole table.


class BankPassageRow(Base):
    __tablename__ = "bank_passages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    skill: Mapped[str] = mapped_column(String(16))
    level: Mapped[str] = mapped_column(String(2))
    topic: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    audio: Mapped[str | None] = mapped_column(String(200))
    duration_s: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))
    quality: Mapped[float] = mapped_column(Float)
    source: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class BankQuestionRow(Base):
    __tablename__ = "bank_questions"
    __table_args__ = (
        Index("ix_bank_questions_pick", "skill", "status", "level", "rand"),
        Index("ix_bank_questions_rand", "skill", "status", "rand"),
        Index("ix_bank_questions_point", "skill", "point", "level", "rand"),
        Index("ix_bank_questions_topic", "skill", "topic", "level", "rand"),
        Index("ix_bank_questions_passage", "passage_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    skill: Mapped[str] = mapped_column(String(16))
    skill_id: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(2))
    topic: Mapped[str] = mapped_column(String(32))
    point: Mapped[str] = mapped_column(String(48))
    qtype: Mapped[str] = mapped_column(String(16))
    difficulty: Mapped[str] = mapped_column(String(8))
    passage_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    quality: Mapped[float] = mapped_column(Float)
    rand: Mapped[float] = mapped_column(Float)
    content_hash: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)  # prompt, options, answer, explanations
    # a person's review decision (approved / disabled); the importer keeps it while the
    # question's content is unchanged
    reviewed_by: Mapped[str | None] = mapped_column(String(36))
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class LearnerQuestionStatRow(Base):
    """One row per learner and question: anti-repetition, review of wrong answers."""

    __tablename__ = "learner_question_stats"
    __table_args__ = (Index("ix_learner_question_stats_seen", "learner_id", "last_seen"),)

    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    skill: Mapped[str] = mapped_column(String(16))
    passage_id: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer)
    correct: Mapped[int] = mapped_column(Integer)
    wrong: Mapped[int] = mapped_column(Integer)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime)
    last_correct: Mapped[bool] = mapped_column(Boolean)


class BankImportRow(Base):
    """What was imported into the bank tables, and from which bank manifest."""

    __tablename__ = "bank_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manifest_hash: Mapped[str] = mapped_column(String(64))
    questions: Mapped[int] = mapped_column(Integer)
    passages: Mapped[int] = mapped_column(Integer)
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime)
