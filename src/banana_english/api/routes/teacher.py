"""Teachers (and admins): the progress and results of the students assigned to them.

Every student endpoint goes through TeacherScope.require_student first: a teacher gets 403
for a student who is not theirs, whatever id they send (no IDOR). The views are the same ones
the learner sees for themselves.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from banana_english.api.deps import ERRORS, ContainerDep, StudentViewer, require
from banana_english.api.routes.admin import user_view
from banana_english.api.routes.learner import (
    activity_view,
    attempts_view,
    mastery_view,
    weak_skills_view,
)
from banana_english.api.schemas import admin as a
from banana_english.api.schemas import modules as m
from banana_english.domain.services.access import Permission

router = APIRouter(
    prefix="/api/v1/teacher",
    tags=["teacher"],
    dependencies=[Depends(require(Permission.VIEW_STUDENTS))],
    responses=ERRORS,
)


@router.get("/students", response_model=a.UsersResponse, summary="My students")
def students(
    teacher: StudentViewer,
    c_: ContainerDep,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    found, total = c_.teacher.students(teacher, q, limit, offset)
    return a.UsersResponse(total=total, users=[user_view(u) for u in found])


@router.get(
    "/students/{student_id}/progress",
    response_model=a.StudentProgressResponse,
    summary="A student's mastery, weak skills and activity",
)
def student_progress(
    student_id: str,
    teacher: StudentViewer,
    c_: ContainerDep,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
):
    student = c_.teacher.require_student(teacher, student_id)
    return a.StudentProgressResponse(
        student=user_view(student),
        mastery=mastery_view(c_, student_id),
        weak_skills=weak_skills_view(c_, student_id, 10),
        activity=activity_view(c_, student_id, days),
    )


@router.get(
    "/students/{student_id}/attempts",
    response_model=list[m.RecentAttemptView],
    summary="A student's recent answers and results",
)
def student_attempts(
    student_id: str,
    teacher: StudentViewer,
    c_: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
):
    c_.teacher.require_student(teacher, student_id)
    return attempts_view(c_, student_id, limit)
