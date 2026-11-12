"""What a teacher may see of other learners: only the students an admin assigned to them.

The scope check (`require_student`) is the one place that decides whether an actor may read a
student's progress; every teacher endpoint calls it before reusing the learner queries. An
admin may read any user. Knowing a user id is never enough (IDOR).
"""

from __future__ import annotations

from banana_english.application.use_cases.common import (
    ForbiddenError,
    NotFoundError,
    UowFactory,
    require_permission,
)
from banana_english.domain.models import Principal, Role, UserSummary
from banana_english.domain.services.access import Permission

MAX_PAGE = 200


class TeacherScope:
    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow_factory = uow_factory

    def students(
        self, actor: Principal, query: str = "", limit: int = 50, offset: int = 0
    ) -> tuple[list[UserSummary], int]:
        """A teacher's students; for an admin, every student."""
        require_permission(actor, Permission.VIEW_STUDENTS)
        with self._uow_factory() as uow:
            only = None if actor.role is Role.ADMIN else uow.users.student_ids(actor.user_id)
            if only is not None and not only:
                return [], 0
            return uow.users.search(
                query, Role.STUDENT, None, min(limit, MAX_PAGE), max(offset, 0), only_ids=only
            )

    def require_student(self, actor: Principal, student_id: str) -> UserSummary:
        """The student, if the actor may read their progress; 403 otherwise."""
        require_permission(actor, Permission.VIEW_STUDENTS)
        with self._uow_factory() as uow:
            if actor.role is not Role.ADMIN and not uow.users.is_linked(actor.user_id, student_id):
                raise ForbiddenError("this student is not assigned to you")
            summary = uow.users.summary(student_id)
            if summary is None:
                raise NotFoundError(f"student {student_id}")
            return summary
