from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Self

from sqlalchemy import Engine, Integer, cast, create_engine, event, func, inspect, select
from sqlalchemy.orm import Session, selectinload, sessionmaker
from sqlalchemy.pool import StaticPool

from banana_english.domain.interfaces.recommendation import ItemHistory
from banana_english.domain.models import (
    Account,
    Assessment,
    Assessor,
    Attempt,
    AttemptStatus,
    AuthSession,
    CefrLevel,
    Conversation,
    ConversationStatus,
    ConversationTurn,
    Job,
    JobStatus,
    LearnerProfile,
    MasteryEvent,
    Mistake,
    MistakeCategory,
    Module,
    SkillMastery,
    User,
    VocabularyCard,
)
from banana_english.domain.models.skills import COMPANION_SKILLS
from banana_english.infrastructure.database.bank_repository import (
    SqlQuestionBank,
    SqlQuestionStats,
)
from banana_english.infrastructure.database.tables import (
    AccountRow,
    AttemptRow,
    ConversationRow,
    JobRow,
    LearnerProfileRow,
    LLMCallRow,
    MasteryEventRow,
    MistakeRow,
    SessionRow,
    SkillMasteryRow,
    UserRow,
    VocabularyCardRow,
)
from banana_english.infrastructure.database.user_repository import (
    SqlSystemStats,
    SqlUserDirectory,
    user_from_row,
)


def create_db_engine(url: str) -> Engine:
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record) -> None:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    _wait_for_database(engine)
    migrate(engine)
    return engine


def _wait_for_database(engine: Engine, attempts: int = 30, delay_seconds: float = 2.0) -> None:
    """The database may start after the API (e.g. after a host reboot): wait instead of
    crash-looping. Gives up after ~1 minute with the original error."""
    import logging
    import time

    from sqlalchemy.exc import OperationalError

    log = logging.getLogger("banana_english.db")
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect():
                return
        except OperationalError as exc:
            if attempt == attempts:
                raise
            log.warning(
                "database not reachable (attempt %d/%d): %s",
                attempt,
                attempts,
                str(exc).splitlines()[0],
            )
            time.sleep(delay_seconds)


MIGRATIONS = Path(__file__).parent / "migrations"


def migrate(engine: Engine) -> None:
    """Bring the schema to the latest Alembic revision.

    A database created by the pre-migration `create_all` (it has tables but no alembic_version)
    is stamped at the initial revision first, then upgraded — no data is touched.
    """
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "users" in tables and "alembic_version" not in tables:
            command.stamp(config, "0001")
        command.upgrade(config, "head")


# --- learners ----------------------------------------------------------------------------


class SqlLearnerRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, user: User, profile: LearnerProfile) -> None:
        self._s.add(UserRow(id=user.id, display_name=user.display_name, created_at=user.created_at))
        self._s.flush()
        self._s.add(
            LearnerProfileRow(
                user_id=profile.user_id,
                current_level=profile.current_level.value,
                target_level=profile.target_level.value,
                native_language=profile.native_language,
                created_at=profile.created_at,
            )
        )

    def get(self, user_id: str) -> tuple[User, LearnerProfile] | None:
        row = self._s.get(UserRow, user_id)
        prof = self._s.get(LearnerProfileRow, user_id)
        if row is None or prof is None:
            return None
        return (
            user_from_row(row),
            LearnerProfile(
                prof.user_id,
                CefrLevel(prof.current_level),
                CefrLevel(prof.target_level),
                prof.native_language,
                prof.created_at,
            ),
        )


# --- mastery -----------------------------------------------------------------------------


class SqlMasteryRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    @staticmethod
    def _from_row(r: SkillMasteryRow) -> SkillMastery:
        return SkillMastery(
            r.learner_id,
            r.skill_id,
            r.mastery,
            r.confidence,
            r.attempt_count,
            r.correct_count,
            r.last_practiced_at,
        )

    def get(self, learner_id: str, skill_id: str) -> SkillMastery | None:
        row = self._s.get(SkillMasteryRow, (learner_id, skill_id))
        return self._from_row(row) if row else None

    def list(self, learner_id: str) -> list[SkillMastery]:
        rows = self._s.scalars(
            select(SkillMasteryRow)
            .where(SkillMasteryRow.learner_id == learner_id)
            .order_by(SkillMasteryRow.skill_id)
        )
        return [self._from_row(r) for r in rows]

    def save(self, m: SkillMastery) -> None:
        self._s.merge(
            SkillMasteryRow(
                learner_id=m.learner_id,
                skill_id=m.skill_id,
                mastery=m.mastery,
                confidence=m.confidence,
                attempt_count=m.attempt_count,
                correct_count=m.correct_count,
                last_practiced_at=m.last_practiced_at,
            )
        )

    def add_event(self, e: MasteryEvent) -> None:
        self._s.add(
            MasteryEventRow(
                learner_id=e.learner_id,
                skill_id=e.skill_id,
                attempt_id=e.attempt_id,
                source=e.source,
                score=e.score,
                mastery_before=e.mastery_before,
                mastery_after=e.mastery_after,
                at=e.at,
            )
        )

    def events(
        self, learner_id: str, since: datetime, skill_id: str | None = None
    ) -> list[MasteryEvent]:
        stmt = (
            select(MasteryEventRow)
            .where(MasteryEventRow.learner_id == learner_id, MasteryEventRow.at >= since)
            .order_by(MasteryEventRow.at, MasteryEventRow.id)
        )
        if skill_id:
            stmt = stmt.where(MasteryEventRow.skill_id == skill_id)
        return [
            MasteryEvent(
                r.learner_id,
                r.skill_id,
                r.score,
                r.mastery_before,
                r.mastery_after,
                r.at,
                r.attempt_id,
                r.source,
            )
            for r in self._s.scalars(stmt)
        ]

    def active_days(self, learner_id: str, since: datetime) -> dict[date, int]:
        rows = self._s.scalars(
            select(AttemptRow.submitted_at).where(
                AttemptRow.learner_id == learner_id,
                AttemptRow.submitted_at >= since,
                AttemptRow.status == AttemptStatus.ASSESSED.value,
                AttemptRow.skill_id.not_in(COMPANION_SKILLS),
            )
        )
        days: Counter[date] = Counter(at.astimezone(UTC).date() for at in rows)
        return dict(days)


# --- attempts ----------------------------------------------------------------------------


def _attempt_from_row(r: AttemptRow) -> Attempt:
    assessment = None
    if r.status == AttemptStatus.ASSESSED.value and r.score is not None:
        assessment = Assessment(
            score=r.score,
            is_correct=bool(r.is_correct),
            feedback=r.feedback or "",
            assessor=Assessor(r.assessor),
            mistakes=tuple(
                Mistake(MistakeCategory(m.category), m.explanation, m.fragment, m.correction)
                for m in r.mistakes
            ),
            corrected_answer=r.corrected_answer,
            prompt_version=r.prompt_version,
            model=r.model,
        )
    return Attempt(
        r.id,
        r.learner_id,
        Module(r.module),
        r.item_id,
        r.skill_id,
        r.answer,
        r.submitted_at,
        AttemptStatus(r.status),
        r.response_time_ms,
        assessment,
        dict(r.details or {}),
    )


class SqlAttemptRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, attempt: Attempt) -> None:
        a = attempt.assessment
        self._s.add(
            AttemptRow(
                id=attempt.id,
                learner_id=attempt.learner_id,
                module=attempt.module.value,
                item_id=attempt.item_id,
                skill_id=attempt.skill_id,
                answer=attempt.answer,
                submitted_at=attempt.submitted_at,
                status=attempt.status.value,
                response_time_ms=attempt.response_time_ms,
                score=a.score if a else None,
                is_correct=a.is_correct if a else None,
                feedback=a.feedback if a else None,
                assessor=a.assessor.value if a else None,
                corrected_answer=a.corrected_answer if a else None,
                prompt_version=a.prompt_version if a else None,
                model=a.model if a else None,
                details=attempt.details,
                mistakes=[
                    MistakeRow(
                        category=m.category.value,
                        explanation=m.explanation,
                        fragment=m.fragment,
                        correction=m.correction,
                    )
                    for m in (a.mistakes if a else ())
                ],
            )
        )

    def get(self, attempt_id: str) -> Attempt | None:
        row = self._s.get(AttemptRow, attempt_id, options=[selectinload(AttemptRow.mistakes)])
        return _attempt_from_row(row) if row else None

    def count(self, learner_id: str) -> tuple[int, int]:
        # cast: SUM over a Boolean column is typed Boolean and would collapse to True/False
        total, correct = self._s.execute(
            select(
                func.count(), func.coalesce(func.sum(cast(AttemptRow.is_correct, Integer)), 0)
            ).where(
                AttemptRow.learner_id == learner_id,
                AttemptRow.status == AttemptStatus.ASSESSED.value,
                AttemptRow.skill_id.not_in(COMPANION_SKILLS),
            )
        ).one()
        return int(total), int(correct)

    def item_history(self, learner_id: str) -> dict[str, ItemHistory]:
        rows = self._s.execute(
            select(AttemptRow.item_id, AttemptRow.submitted_at, AttemptRow.is_correct)
            .where(
                AttemptRow.learner_id == learner_id,
                AttemptRow.status == AttemptStatus.ASSESSED.value,
                AttemptRow.skill_id.not_in(COMPANION_SKILLS),
            )
            .order_by(AttemptRow.submitted_at, AttemptRow.id)
        )
        history: dict[str, ItemHistory] = {}
        for item_id, at, correct in rows:
            prev = history.get(item_id)
            history[item_id] = ItemHistory(
                attempts=(prev.attempts if prev else 0) + 1,
                last_correct=bool(correct),
                last_attempted_at=at,
                ever_correct=bool(correct) or (prev.ever_correct if prev else False),
            )
        return history

    def recent_mistake_counts(self, learner_id: str, limit: int = 50) -> dict[str, dict[str, int]]:
        recent = self._s.scalars(
            select(AttemptRow)
            .options(selectinload(AttemptRow.mistakes))
            .where(
                AttemptRow.learner_id == learner_id,
                AttemptRow.status == AttemptStatus.ASSESSED.value,
            )
            .order_by(AttemptRow.submitted_at.desc(), AttemptRow.id.desc())
            .limit(limit)
        )
        counts: dict[str, Counter[str]] = defaultdict(Counter)
        for attempt in recent:
            for m in attempt.mistakes:
                counts[attempt.skill_id][m.category] += 1
        return {skill: dict(c) for skill, c in counts.items()}

    def recent(self, learner_id: str, limit: int = 20) -> list[Attempt]:
        rows = self._s.scalars(
            select(AttemptRow)
            .options(selectinload(AttemptRow.mistakes))
            .where(
                AttemptRow.learner_id == learner_id,
                AttemptRow.skill_id.not_in(COMPANION_SKILLS),
            )
            .order_by(AttemptRow.submitted_at.desc(), AttemptRow.id.desc())
            .limit(limit)
        )
        return [_attempt_from_row(r) for r in rows]


# --- vocabulary cards --------------------------------------------------------------------


def _card_from_row(r: VocabularyCardRow) -> VocabularyCard:
    return VocabularyCard(
        r.learner_id,
        r.item_id,
        r.repetitions,
        r.ease_factor,
        r.interval_days,
        r.due_date,
        r.last_reviewed_at,
        r.lapses,
        r.review_count,
        r.created_at,
    )


class SqlCardRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, learner_id: str, item_id: str) -> VocabularyCard | None:
        row = self._s.get(VocabularyCardRow, (learner_id, item_id))
        return _card_from_row(row) if row else None

    def save(self, c: VocabularyCard) -> None:
        self._s.merge(
            VocabularyCardRow(
                learner_id=c.learner_id,
                item_id=c.item_id,
                repetitions=c.repetitions,
                ease_factor=c.ease_factor,
                interval_days=c.interval_days,
                due_date=c.due_date,
                last_reviewed_at=c.last_reviewed_at,
                lapses=c.lapses,
                review_count=c.review_count,
                created_at=c.created_at,
            )
        )

    def list_due(self, learner_id: str, today: date, limit: int) -> list[VocabularyCard]:
        rows = self._s.scalars(
            select(VocabularyCardRow)
            .where(VocabularyCardRow.learner_id == learner_id, VocabularyCardRow.due_date <= today)
            .order_by(VocabularyCardRow.due_date, VocabularyCardRow.item_id)
            .limit(limit)
        )
        return [_card_from_row(r) for r in rows]

    def seen_item_ids(self, learner_id: str) -> frozenset[str]:
        return frozenset(
            self._s.scalars(
                select(VocabularyCardRow.item_id).where(VocabularyCardRow.learner_id == learner_id)
            )
        )

    def created_since(self, learner_id: str, since: datetime) -> int:
        return int(
            self._s.scalar(
                select(func.count())
                .select_from(VocabularyCardRow)
                .where(
                    VocabularyCardRow.learner_id == learner_id,
                    VocabularyCardRow.created_at >= since,
                )
            )
            or 0
        )


# --- conversations & jobs ----------------------------------------------------------------


class SqlConversationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    @staticmethod
    def _to_row(c: Conversation) -> ConversationRow:
        return ConversationRow(
            id=c.id,
            learner_id=c.learner_id,
            scenario_id=c.scenario_id,
            status=c.status.value,
            turns=[{"role": t.role, "text": t.text, "at": t.at.isoformat()} for t in c.turns],
            summary=c.summary,
            created_at=c.created_at,
        )

    def add(self, c: Conversation) -> None:
        self._s.add(self._to_row(c))

    def save(self, c: Conversation) -> None:
        self._s.merge(self._to_row(c))

    def get(self, conversation_id: str) -> Conversation | None:
        r = self._s.get(ConversationRow, conversation_id)
        if r is None:
            return None
        turns = tuple(
            ConversationTurn(t["role"], t["text"], datetime.fromisoformat(t["at"])) for t in r.turns
        )
        return Conversation(
            r.id,
            r.learner_id,
            r.scenario_id,
            ConversationStatus(r.status),
            turns,
            r.created_at,
            r.summary,
        )


class SqlJobRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, j: Job) -> None:
        self._s.add(
            JobRow(
                id=j.id,
                learner_id=j.learner_id,
                kind=j.kind,
                status=j.status.value,
                result=j.result,
                error=j.error,
                created_at=j.created_at,
                updated_at=j.updated_at,
            )
        )

    def save(self, j: Job) -> None:
        self._s.merge(
            JobRow(
                id=j.id,
                learner_id=j.learner_id,
                kind=j.kind,
                status=j.status.value,
                result=j.result,
                error=j.error,
                created_at=j.created_at,
                updated_at=j.updated_at,
            )
        )

    def get(self, job_id: str) -> Job | None:
        r = self._s.get(JobRow, job_id)
        return (
            Job(
                r.id,
                r.learner_id,
                r.kind,
                JobStatus(r.status),
                r.created_at,
                r.updated_at,
                r.result,
                r.error,
            )
            if r
            else None
        )


class SqlLLMCallLog:
    """Writes the llm_calls audit table in its own short transaction."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, entry: dict[str, Any]) -> None:
        with self._session_factory() as s:
            s.add(LLMCallRow(**entry))
            s.commit()

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._session_factory() as s:
            rows = s.scalars(select(LLMCallRow).order_by(LLMCallRow.id.desc()).limit(limit))
            return [
                {c.name: getattr(r, c.name) for c in LLMCallRow.__table__.columns} for r in rows
            ]


class SqlAuthRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add_account(self, a: Account) -> None:
        self._s.add(
            AccountRow(
                user_id=a.user_id,
                email=a.email,
                password_hash=a.password_hash,
                created_at=a.created_at,
            )
        )

    def account_by_email(self, email: str) -> Account | None:
        row = self._s.scalar(select(AccountRow).where(AccountRow.email == email))
        return Account(row.user_id, row.email, row.password_hash, row.created_at) if row else None

    def add_session(self, s: AuthSession) -> None:
        self._s.add(
            SessionRow(
                token_hash=s.token_hash,
                user_id=s.user_id,
                created_at=s.created_at,
                expires_at=s.expires_at,
            )
        )

    def get_session(self, token_hash: str) -> AuthSession | None:
        row = self._s.get(SessionRow, token_hash)
        return (
            AuthSession(row.token_hash, row.user_id, row.created_at, row.expires_at)
            if row
            else None
        )

    def delete_session(self, token_hash: str) -> None:
        row = self._s.get(SessionRow, token_hash)
        if row is not None:
            self._s.delete(row)

    def session_user(self, token_hash: str) -> tuple[AuthSession, User] | None:
        """The session and its user in one query: every request needs both (role, status)."""
        found = self._s.execute(
            select(SessionRow, UserRow)
            .join(UserRow, UserRow.id == SessionRow.user_id)
            .where(SessionRow.token_hash == token_hash)
        ).one_or_none()
        if found is None:
            return None
        row, user = found
        return (
            AuthSession(row.token_hash, row.user_id, row.created_at, row.expires_at),
            user_from_row(user),
        )


class SqlUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.learners = SqlLearnerRepository(self._session)
        self.auth = SqlAuthRepository(self._session)
        self.mastery = SqlMasteryRepository(self._session)
        self.attempts = SqlAttemptRepository(self._session)
        self.cards = SqlCardRepository(self._session)
        self.conversations = SqlConversationRepository(self._session)
        self.jobs = SqlJobRepository(self._session)
        self.bank = SqlQuestionBank(self._session)
        self.question_stats = SqlQuestionStats(self._session)
        self.users = SqlUserDirectory(self._session)
        self.system = SqlSystemStats(self._session)
        return self

    def __exit__(self, *exc: object) -> None:
        self._session.rollback()  # no-op after commit; discards anything uncommitted
        self._session.close()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
