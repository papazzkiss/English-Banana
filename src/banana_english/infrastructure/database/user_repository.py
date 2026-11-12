"""Users as the admin and teacher screens see them: lists with learning totals, role and status
changes, and the teacher-student links that scope what a teacher may read."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Integer, and_, cast, delete, func, or_, select, update
from sqlalchemy.orm import Session

from banana_english.domain.models import AttemptStatus, Role, User, UserSummary
from banana_english.infrastructure.database.tables import (
    AccountRow,
    AttemptRow,
    SessionRow,
    TeacherStudentRow,
    UserRow,
)


def user_from_row(row: UserRow) -> User:
    return User(row.id, row.display_name, row.created_at, Role(row.role), bool(row.is_active))


class SqlUserDirectory:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, user_id: str) -> User | None:
        row = self._s.get(UserRow, user_id)
        return user_from_row(row) if row is not None else None

    def email(self, user_id: str) -> str | None:
        return self._s.scalar(select(AccountRow.email).where(AccountRow.user_id == user_id))

    def search(
        self,
        query: str = "",
        role: Role | None = None,
        active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        only_ids: Sequence[str] | None = None,
    ) -> tuple[list[UserSummary], int]:
        """Users matching name/e-mail, newest first, with their totals; and the match count."""
        base = select(UserRow, AccountRow.email).outerjoin(
            AccountRow, AccountRow.user_id == UserRow.id
        )
        conditions = []
        if query.strip():
            like = f"%{query.strip().lower()}%"
            conditions.append(
                or_(func.lower(UserRow.display_name).like(like), AccountRow.email.like(like))
            )
        if role is not None:
            conditions.append(UserRow.role == role.value)
        if active is not None:
            conditions.append(UserRow.is_active.is_(active))
        if only_ids is not None:
            conditions.append(UserRow.id.in_(list(only_ids)))
        if conditions:
            base = base.where(and_(*conditions))
        total = int(self._s.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = self._s.execute(
            base.order_by(UserRow.created_at.desc(), UserRow.id).limit(limit).offset(offset)
        ).all()
        totals = self._totals([r[0].id for r in rows])
        return [
            UserSummary(user_from_row(u), email, *totals.get(u.id, (0, 0, None)))
            for u, email in rows
        ], total

    def summary(self, user_id: str) -> UserSummary | None:
        found, _ = self.search(only_ids=[user_id], limit=1)
        return found[0] if found else None

    def _totals(self, user_ids: list[str]) -> dict[str, tuple[int, int, datetime | None]]:
        """Assessed attempts, correct ones, last attempt: one grouped query for the page."""
        if not user_ids:
            return {}
        rows = self._s.execute(
            select(
                AttemptRow.learner_id,
                func.count(),
                func.coalesce(func.sum(cast(AttemptRow.is_correct, Integer)), 0),
                func.max(AttemptRow.submitted_at),
            )
            .where(
                AttemptRow.learner_id.in_(user_ids),
                AttemptRow.status == AttemptStatus.ASSESSED.value,
            )
            .group_by(AttemptRow.learner_id)
        )
        return {lid: (int(n), int(ok), last) for lid, n, ok, last in rows}

    # --- changes -------------------------------------------------------------------------
    def set_role(self, user_id: str, role: Role) -> None:
        self._s.execute(update(UserRow).where(UserRow.id == user_id).values(role=role.value))

    def set_active(self, user_id: str, active: bool) -> None:
        self._s.execute(update(UserRow).where(UserRow.id == user_id).values(is_active=active))

    def revoke_sessions(self, user_id: str) -> int:
        """Sign the user out everywhere (after deactivation or a role change)."""
        result = self._s.execute(delete(SessionRow).where(SessionRow.user_id == user_id))
        return int(result.rowcount or 0)

    def count_active(self, role: Role) -> int:
        return int(
            self._s.scalar(
                select(func.count())
                .select_from(UserRow)
                .where(UserRow.role == role.value, UserRow.is_active.is_(True))
            )
            or 0
        )

    def counts(self) -> dict[str, dict[str, int]]:
        """Users per role, split into active and inactive."""
        out: dict[str, dict[str, int]] = {r.value: {"active": 0, "inactive": 0} for r in Role}
        rows = self._s.execute(
            select(UserRow.role, UserRow.is_active, func.count()).group_by(
                UserRow.role, UserRow.is_active
            )
        )
        for role, active, n in rows:
            out.setdefault(role, {"active": 0, "inactive": 0})
            out[role]["active" if active else "inactive"] += int(n)
        return out

    def created_since(self, since: datetime) -> int:
        return int(
            self._s.scalar(
                select(func.count()).select_from(UserRow).where(UserRow.created_at >= since)
            )
            or 0
        )

    # --- teacher scope -------------------------------------------------------------------
    def link(self, teacher_id: str, student_id: str, at: datetime) -> bool:
        if self.is_linked(teacher_id, student_id):
            return False
        self._s.add(TeacherStudentRow(teacher_id=teacher_id, student_id=student_id, created_at=at))
        return True

    def unlink(self, teacher_id: str, student_id: str) -> bool:
        result = self._s.execute(
            delete(TeacherStudentRow).where(
                TeacherStudentRow.teacher_id == teacher_id,
                TeacherStudentRow.student_id == student_id,
            )
        )
        return bool(result.rowcount)

    def is_linked(self, teacher_id: str, student_id: str) -> bool:
        return (
            self._s.get(TeacherStudentRow, {"teacher_id": teacher_id, "student_id": student_id})
            is not None
        )

    def student_ids(self, teacher_id: str) -> list[str]:
        return list(
            self._s.scalars(
                select(TeacherStudentRow.student_id).where(
                    TeacherStudentRow.teacher_id == teacher_id
                )
            )
        )

    def teacher_ids(self, student_id: str) -> list[str]:
        return list(
            self._s.scalars(
                select(TeacherStudentRow.teacher_id).where(
                    TeacherStudentRow.student_id == student_id
                )
            )
        )

    def unlink_all(self, user_id: str) -> None:
        """Drop every link of a user (it stopped being a teacher, or a student)."""
        self._s.execute(
            delete(TeacherStudentRow).where(
                or_(
                    TeacherStudentRow.teacher_id == user_id,
                    TeacherStudentRow.student_id == user_id,
                )
            )
        )


class SqlSystemStats:
    """Platform-wide numbers for the admin dashboard (read-only)."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def attempts(self, since: datetime) -> dict[str, int]:
        total = int(self._s.scalar(select(func.count()).select_from(AttemptRow)) or 0)
        recent, learners = self._s.execute(
            select(func.count(), func.count(func.distinct(AttemptRow.learner_id))).where(
                AttemptRow.submitted_at >= since
            )
        ).one()
        by_module = dict(
            self._s.execute(
                select(AttemptRow.module, func.count())
                .where(AttemptRow.submitted_at >= since)
                .group_by(AttemptRow.module)
            ).all()
        )
        return {
            "total": total,
            "recent": int(recent),
            "active_learners": int(learners),
            **{f"recent_{k}": int(v) for k, v in by_module.items()},
        }
