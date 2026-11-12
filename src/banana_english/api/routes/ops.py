from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from banana_english.api.deps import ContainerDep, optional_principal
from banana_english.api.schemas.modules import FeaturesResponse
from banana_english.application.services.prompts import (
    CONVERSATION_REPLY_VERSION,
    GRAMMAR_ASSESSMENT_VERSION,
    LISTENING_ASSESSMENT_VERSION,
    MONKEY_CHAT_VERSION,
    TUTOR_EXPLAIN_VERSION,
)
from banana_english.domain.models import Principal
from banana_english.domain.services.access import Permission, can

router = APIRouter()


@router.get("/health", tags=["ops"], summary="Liveness")
def health() -> dict:
    return {"status": "ok"}


def system_summary(c_) -> dict:
    """Model, providers, prompt versions and content status: for admins only."""
    return {
        "llm_provider": c_.llm.name,
        "llm": {
            "model": c_.settings.ollama_model if c_.settings.llm_provider == "ollama" else None,
            "fallback_model": c_.settings.llm_fallback_model,
            "context_length": c_.settings.llm_context_length,
            "timeout_seconds": c_.settings.llm_timeout_seconds,
            "keep_alive": c_.settings.llm_keep_alive,
        },
        "stt_provider": c_.stt.name,
        "prompt_versions": {
            "grammar": GRAMMAR_ASSESSMENT_VERSION,
            "listening": LISTENING_ASSESSMENT_VERSION,
            "conversation": CONVERSATION_REPLY_VERSION,
            "tutor": TUTOR_EXPLAIN_VERSION,
            "monkey": MONKEY_CHAT_VERSION,
        },
        "skills": len(c_.content.list_skills()),
        "content_review_status": c_.content.review_counts,
        "require_reviewed_content": c_.settings.require_reviewed_content,
        "feature_ai_monkey": c_.settings.feature_ai_monkey,
    }


@router.get(
    "/api/v1/health",
    tags=["ops"],
    summary="Liveness; the configuration summary is included for admins only",
)
def health_details(
    c_: ContainerDep, principal: Annotated[Principal | None, Depends(optional_principal)]
) -> dict:
    # This path is reachable from the internet through the web proxy: the model, timeouts
    # and prompt versions are not for everyone.
    if principal is None or not can(principal.role, Permission.VIEW_SYSTEM):
        return {"status": "ok"}
    return {"status": "ok", **system_summary(c_)}


@router.get(
    "/api/v1/features",
    response_model=FeaturesResponse,
    tags=["ops"],
    summary="Feature flags the web app uses to show or hide features",
)
def features(c_: ContainerDep):
    return FeaturesResponse(ai_monkey=c_.settings.feature_ai_monkey)


@router.get("/metrics", tags=["ops"], summary="Prometheus metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
