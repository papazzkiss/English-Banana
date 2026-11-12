"""Administration: users (role, status, teacher links) and platform statistics.

Every method takes the acting Principal and checks its permission itself, so a route that
forgot its dependency still cannot be used by the wrong role. Nothing is ever deleted: an
account is deactivated (and signed out everywhere), which keeps its learning history.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from banana_english.application.use_cases.common import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    UowFactory,
    require_permission,
)
from banana_english.domain.interfaces.infra import Clock
from banana_english.domain.models import Principal, Role, UserSummary
from banana_english.domain.services.access import Permission

log = logging.getLogger("banana_english.admin")
MAX_PAGE = 200
RECENT = timedelta(days=7)


@dataclass(frozen=True)
class UserDetail:
    summary: UserSummary
    teacher_ids: list[str]  # the teachers following this user
    student_ids: list[str]  # the students this user follows (teachers)


class UserAdministration:
    def __init__(self, uow_factory: UowFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def list_users(
        self,
        actor: Principal,
        query: str = "",
        role: Role | None = None,
        active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[UserSummary], int]:
        require_permission(actor, Permission.MANAGE_USERS)
        with self._uow_factory() as uow:
            return uow.users.search(query, role, active, min(limit, MAX_PAGE), max(offset, 0))

    def user_detail(self, actor: Principal, user_id: str) -> UserDetail:
        require_permission(actor, Permission.MANAGE_USERS)
        with self._uow_factory() as uow:
            summary = uow.users.summary(user_id)
            if summary is None:
                raise NotFoundError(f"user {user_id}")
            return UserDetail(
                summary, uow.users.teacher_ids(user_id), uow.users.student_ids(user_id)
            )

    def update_user(
        self,
        actor: Principal,
        user_id: str,
        role: Role | None = None,
        is_active: bool | None = None,
    ) -> UserDetail:
        """Change a user's role and/or status. An admin cannot change their own role or
        status, and the last active admin cannot be demoted or disabled (no lock-out)."""
        require_permission(actor, Permission.MANAGE_USERS)
        with self._uow_factory() as uow:
            user = uow.users.get(user_id)
            if user is None:
                raise NotFoundError(f"user {user_id}")
            role_change = role is not None and role != user.role
            status_change = is_active is not None and is_active != user.is_active
            if not (role_change or status_change):
                return self._detail(uow, user_id)
            if user_id == actor.user_id:
                raise ForbiddenError("you cannot change your own role or status")
            losing_admin = (
                user.role is Role.ADMIN and user.is_active and (role_change or is_active is False)
            )
            if losing_admin and uow.users.count_active(Role.ADMIN) <= 1:
                raise ConflictError("this is the last active admin")
            if role_change:
                uow.users.set_role(user_id, role)
                uow.users.unlink_all(user_id)  # teacher links belong to the old role
            if status_change:
                uow.users.set_active(user_id, bool(is_active))
                if not is_active:
                    uow.users.revoke_sessions(user_id)  # signed out everywhere, now
            uow.commit()
            log.info(  # audit trail in the JSON log
                "user %s updated by admin %s: role %s, active %s",
                user_id,
                actor.user_id,
                f"{user.role} -> {role}" if role_change else "unchanged",
                f"{user.is_active} -> {is_active}" if status_change else "unchanged",
            )
            return self._detail(uow, user_id)

    def link_student(self, actor: Principal, teacher_id: str, student_id: str, linked: bool):
        """Let a teacher follow a student (or stop)."""
        require_permission(actor, Permission.MANAGE_USERS)
        with self._uow_factory() as uow:
            teacher, student = uow.users.get(teacher_id), uow.users.get(student_id)
            if teacher is None or student is None:
                raise NotFoundError("user")
            if teacher.role is not Role.TEACHER:
                raise InvalidInputError("only a teacher can follow students")
            if student.role is not Role.STUDENT:
                raise InvalidInputError("a teacher can only follow students")
            if linked:
                uow.users.link(teacher_id, student_id, self._clock.now())
            else:
                uow.users.unlink(teacher_id, student_id)
            uow.commit()
            return self._detail(uow, teacher_id)

    def system_stats(self, actor: Principal) -> dict[str, Any]:
        require_permission(actor, Permission.VIEW_SYSTEM)
        since = self._clock.now() - RECENT
        with self._uow_factory() as uow:
            return {
                "users": uow.users.counts(),
                "new_users_7d": uow.users.created_since(since),
                "attempts": uow.system.attempts(since),
                "bank": uow.bank.status_counts(),
                "bank_last_import": uow.bank.last_import(),
            }

    @staticmethod
    def _detail(uow, user_id: str) -> UserDetail:
        summary = uow.users.summary(user_id)
        return UserDetail(summary, uow.users.teacher_ids(user_id), uow.users.student_ids(user_id))
