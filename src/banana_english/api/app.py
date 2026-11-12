from __future__ import annotations

import json
import logging
import mimetypes
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from banana_english.api.routes import admin, auth, bank, learner, monkey, ops, practice, teacher
from banana_english.application.use_cases.common import (
    AccountDisabledError,
    AssessmentFailedError,
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    LearnerNotFoundError,
    NotFoundError,
    ProviderUnavailableError,
    TooManyAttemptsError,
    UnauthorizedError,
    UseCaseError,
)
from banana_english.config.container import Container, build_container
from banana_english.infrastructure.observability.context import (
    current_request_id,
    reset_request_id,
    set_request_id,
)
from banana_english.infrastructure.observability.metrics import HTTP_LATENCY

# slim images have no /etc/mime.types: without this, bank recordings go out as octet-stream
mimetypes.add_type("audio/ogg", ".ogg")

logger = logging.getLogger("banana_english")

_STATUS = {
    UnauthorizedError: 401,
    ForbiddenError: 403,
    AccountDisabledError: 403,
    TooManyAttemptsError: 429,
    LearnerNotFoundError: 404,
    NotFoundError: 404,
    ConflictError: 409,
    InvalidInputError: 422,
    AssessmentFailedError: 503,
    ProviderUnavailableError: 503,
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "ts": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
                "request_id": current_request_id(),
            }
        )


def configure_logging(json_logs: bool) -> None:
    root = logging.getLogger("banana_english")
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if json_logs
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def create_app(container: Container | None = None) -> FastAPI:
    container = container or build_container()
    configure_logging(container.settings.log_json)
    pending = {k: v.get("pending_review", 0) for k, v in container.content.review_counts.items()}
    if any(pending.values()):
        logger.warning(
            "Serving AI-generated content that is not human-reviewed yet: %s. "
            "Review with scripts/review_content.py and set "
            "BANANA_REQUIRE_REVIEWED_CONTENT=true for production.",
            pending,
        )

    app = FastAPI(
        title="Banana English API",
        version="1.0.0",
        summary="Adaptive English learning: Learn -> Assess -> Update Mastery -> Recommend.",
    )
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = (request.headers.get("X-Request-ID") or uuid.uuid4().hex)[:64]
        token = set_request_id(request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            HTTP_LATENCY.labels(
                request.method, getattr(route, "path", "unmatched"), str(status)
            ).observe(time.perf_counter() - started)
            reset_request_id(token)

    app.include_router(ops.router)
    app.include_router(auth.router)
    app.include_router(learner.router)
    app.include_router(practice.router)
    app.include_router(monkey.router)
    app.include_router(bank.router)
    app.include_router(teacher.router)
    app.include_router(admin.router)
    app.mount(
        "/media/listening",
        StaticFiles(directory=container.content.audio_dir),
        name="listening-audio",
    )
    # question-bank recordings (content/bank/audio); may not exist before the first build
    app.mount(
        "/media/bank",
        StaticFiles(directory=container.content.content_dir / "bank/audio", check_dir=False),
        name="bank-audio",
    )

    @app.exception_handler(UseCaseError)
    async def _use_case_error(_: Request, exc: UseCaseError) -> JSONResponse:
        details = None
        message = str(exc)
        if isinstance(exc, AssessmentFailedError):
            details = {"attempt_id": exc.attempt_id} if exc.attempt_id else None
            logger.warning("assessment unavailable (attempt %s): %s", exc.attempt_id, exc)
            message = "The answer could not be assessed right now. Please try again."
        elif isinstance(exc, ProviderUnavailableError):
            logger.warning("provider unavailable: %s", exc)
            message = "The AI partner is not available right now. Please try again."
        return _error(_STATUS.get(type(exc), 400), exc.code, message, details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _error(422, "validation_error", "Request validation failed", {"errors": errors})

    return app
