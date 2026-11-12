"""Administration (admins only): users, roles, account status, teacher links, statistics.

The router-level dependency refuses every other role with 403; the use cases check again.
Accounts are never deleted here: deactivate instead (history is kept, sessions are revoked).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from banana_english.api.deps import ERRORS, AdminUser, ContainerDep, SystemViewer, require
from banana_english.api.routes.ops import system_summary
from banana_english.api.schemas import admin as a
from banana_english.api.schemas.common import ErrorResponse
from banana_english.domain.models import Role, UserSummary
from banana_english.domain.services.access import Permission

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require(Permission.MANAGE_USERS))],
    responses=ERRORS,
)
_CHANGE_ERRORS = {
    409: {"model": ErrorResponse, "description": "Would leave no active admin"},
}


def user_view(s: UserSummary) -> a.UserView:
    return a.UserView(
        user_id=s.user.id,
        display_name=s.user.display_name,
        email=s.email,
        role=s.user.role,
        is_active=s.user.is_active,
        created_at=s.user.created_at,
        attempts=s.attempts,
        correct=s.correct,
        last_active=s.last_active,
    )


def _detail(d) -> a.UserDetailView:
    return a.UserDetailView(
        **user_view(d.summary).model_dump(), teacher_ids=d.teacher_ids, student_ids=d.student_ids
    )


@router.get("/users", response_model=a.UsersResponse, summary="Search users")
def list_users(
    admin: AdminUser,
    c_: ContainerDep,
    q: Annotated[str, Query(max_length=100, description="Name or e-mail contains")] = "",
    role: Role | None = None,
    active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    users, total = c_.admin.list_users(admin, q, role, active, limit, offset)
    return a.UsersResponse(total=total, users=[user_view(u) for u in users])


@router.get("/users/{user_id}", response_model=a.UserDetailView, summary="One user")
def get_user(user_id: str, admin: AdminUser, c_: ContainerDep):
    return _detail(c_.admin.user_detail(admin, user_id))


@router.patch(
    "/users/{user_id}",
    response_model=a.UserDetailView,
    responses=_CHANGE_ERRORS,
    summary="Change a user's role and/or activate / deactivate the account",
)
def update_user(user_id: str, body: a.UserUpdateRequest, admin: AdminUser, c_: ContainerDep):
    return _detail(c_.admin.update_user(admin, user_id, body.role, body.is_active))


@router.put(
    "/users/{teacher_id}/students/{student_id}",
    response_model=a.UserDetailView,
    summary="Let a teacher follow a student's progress",
)
def link_student(teacher_id: str, student_id: str, admin: AdminUser, c_: ContainerDep):
    return _detail(c_.admin.link_student(admin, teacher_id, student_id, linked=True))


@router.delete(
    "/users/{teacher_id}/students/{student_id}",
    response_model=a.UserDetailView,
    summary="Stop a teacher following a student",
)
def unlink_student(teacher_id: str, student_id: str, admin: AdminUser, c_: ContainerDep):
    return _detail(c_.admin.link_student(admin, teacher_id, student_id, linked=False))


@router.get("/stats", response_model=a.AdminStatsResponse, summary="Platform statistics")
def stats(admin: SystemViewer, c_: ContainerDep):
    return a.AdminStatsResponse(**c_.admin.system_stats(admin), system=system_summary(c_))
