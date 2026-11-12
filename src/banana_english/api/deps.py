from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from banana_english.api.schemas.common import ErrorResponse
from banana_english.application.use_cases.common import (
    ForbiddenError,
    UnauthorizedError,
    UseCaseError,
)
from banana_english.config.container import Container
from banana_english.domain.models import Principal, Role
from banana_english.domain.services.access import Permission, can

SESSION_COOKIE = "banana_session"
_bearer = HTTPBearer(auto_error=False, description="Session token from /auth/login")
_cookie = APIKeyCookie(
    name=SESSION_COOKIE,
    auto_error=False,
    description="httpOnly session cookie set by /auth/login (web app)",
)


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def session_token(
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    cookie: Annotated[str | None, Depends(_cookie)],
) -> str | None:
    return bearer.credentials if bearer else cookie


def current_principal(
    c_: ContainerDep,
    token: Annotated[str | None, Depends(session_token)],
    x_learner_id: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> Principal:
    """Authenticate -> identify -> account status, in one query. The role comes from the
    database, never from the request. FastAPI resolves this once per request."""
    if token:
        return c_.auth.principal(token)
    if x_learner_id and c_.settings.allow_learner_header:  # dev/test only; never elevated
        return Principal(x_learner_id, Role.STUDENT)
    raise UnauthorizedError("please sign in")


CurrentUser = Annotated[Principal, Depends(current_principal)]


def current_learner(principal: CurrentUser) -> str:
    """Every active account can learn; learning endpoints only ever touch its own data."""
    return principal.user_id


LearnerId = Annotated[str, Depends(current_learner)]


def optional_principal(
    c_: ContainerDep, token: Annotated[str | None, Depends(session_token)]
) -> Principal | None:
    """The signed-in user if any (public endpoints that show more to admins)."""
    if not token:
        return None
    try:
        return c_.auth.principal(token)
    except UseCaseError:
        return None


def require(permission: Permission):
    """A dependency that lets only roles holding `permission` through (403 otherwise)."""

    def check(principal: CurrentUser) -> Principal:
        if not can(principal.role, permission):
            raise ForbiddenError("you do not have access to this")
        return principal

    check.__name__ = f"require_{permission.value}"
    return check


AdminUser = Annotated[Principal, Depends(require(Permission.MANAGE_USERS))]
SystemViewer = Annotated[Principal, Depends(require(Permission.VIEW_SYSTEM))]
Reviewer = Annotated[Principal, Depends(require(Permission.REVIEW_CONTENT))]
StudentViewer = Annotated[Principal, Depends(require(Permission.VIEW_STUDENTS))]

ERRORS = {
    401: {"model": ErrorResponse, "description": "Missing, invalid or expired session"},
    403: {"model": ErrorResponse, "description": "Role not allowed, or account disabled"},
    404: {"model": ErrorResponse, "description": "Item not found"},
    422: {"model": ErrorResponse, "description": "Request validation failed"},
}
LLM_ERRORS = {
    **ERRORS,
    503: {
        "model": ErrorResponse,
        "description": "LLM unavailable or its output invalid after retries. The attempt is "
        "recorded (details.attempt_id); mastery is NOT changed.",
    },
}
