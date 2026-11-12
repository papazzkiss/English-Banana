"""Accounts and sessions. The web app uses the httpOnly cookie; API clients use the token."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from banana_english.api.deps import SESSION_COOKIE, ContainerDep, LearnerId, session_token
from banana_english.api.routes.learner import profile_view
from banana_english.api.schemas import common as c
from banana_english.api.schemas import modules as m
from banana_english.application.use_cases.auth import SignedIn

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_AUTH_ERRORS = {
    401: {"model": c.ErrorResponse, "description": "Wrong e-mail or password"},
    409: {"model": c.ErrorResponse, "description": "E-mail already registered"},
    422: {"model": c.ErrorResponse, "description": "Invalid e-mail or password too short"},
    429: {"model": c.ErrorResponse, "description": "Too many failed logins"},
}


def _signed_in(result: SignedIn, response: Response, c_) -> m.AuthResponse:
    response.set_cookie(
        SESSION_COOKIE,
        result.token,
        max_age=result.expires_in_seconds,
        httponly=True,
        samesite="lax",
        secure=c_.settings.cookie_secure,
        path="/",
    )
    return m.AuthResponse(
        token=result.token,
        expires_in_seconds=result.expires_in_seconds,
        profile=profile_view(result.overview),
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=m.AuthResponse,
    responses=_AUTH_ERRORS,
    summary="Create an account + learner profile, sign in",
)
def register(body: m.RegisterRequest, response: Response, c_: ContainerDep):
    result = c_.auth.register(
        body.email,
        body.password,
        body.display_name,
        body.current_level,
        body.target_level,
        body.native_language,
    )
    return _signed_in(result, response, c_)


@router.post(
    "/login",
    response_model=m.AuthResponse,
    responses=_AUTH_ERRORS,
    summary="Sign in; sets the session cookie and returns a bearer token",
)
def login(body: m.LoginRequest, response: Response, c_: ContainerDep):
    return _signed_in(c_.auth.login(body.email, body.password), response, c_)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke the session")
def logout(
    response: Response, c_: ContainerDep, token: Annotated[str | None, Depends(session_token)]
):
    if token:
        c_.auth.logout(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get(
    "/me",
    response_model=m.LearnerProfileResponse,
    responses={401: _AUTH_ERRORS[401]},
    summary="The signed-in learner",
)
def me(learner_id: LearnerId, c_: ContainerDep):
    return profile_view(c_.learner.profile(learner_id))
