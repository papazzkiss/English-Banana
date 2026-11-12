from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from banana_english.api.app import create_app
from banana_english.config.container import Container, build_container
from banana_english.config.settings import PROJECT_ROOT, Settings
from banana_english.domain.interfaces.infra import Clock
from banana_english.domain.interfaces.llm import LLMProvider
from banana_english.domain.interfaces.stt import STTProvider
from banana_english.infrastructure.ai.mock_llm import HeuristicMockLLMProvider
from banana_english.infrastructure.cache.caches import MemoryCache
from banana_english.infrastructure.content.json_content_repository import JsonContentRepository
from banana_english.infrastructure.jobs.runners import InlineJobRunner
from banana_english.infrastructure.stt.mock_stt import MockSTTProvider

T0 = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


class MutableClock(Clock):
    def __init__(self, start: datetime = T0) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


@pytest.fixture(scope="session")
def content() -> JsonContentRepository:
    return JsonContentRepository(PROJECT_ROOT / "content")


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock()


@pytest.fixture
def make_container(content, clock, tmp_path) -> Callable[..., Container]:
    def _make(llm: LLMProvider | None = None, stt: STTProvider | None = None) -> Container:
        return build_container(
            Settings(database_url="sqlite://", upload_dir=tmp_path / "uploads"),
            llm=llm or HeuristicMockLLMProvider(),
            stt=stt or MockSTTProvider(),
            clock=clock,
            content=content,
            runner=InlineJobRunner(),
            cache=MemoryCache(),
        )

    return _make


@pytest.fixture
def make_client(make_container) -> Callable[..., TestClient]:
    def _make(llm: LLMProvider | None = None, stt: STTProvider | None = None) -> TestClient:
        return TestClient(create_app(make_container(llm, stt)))

    return _make


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def create_learner(client: TestClient, level: str = "A1") -> dict[str, str]:
    """Register a fresh account and return Bearer auth headers for it."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"learner-{uuid.uuid4().hex[:10]}@example.com",
            "password": "correct horse",
            "display_name": "Test Learner",
            "current_level": level,
            "native_language": "vi",
        },
    )
    assert response.status_code == 201, response.text
    # Tests authenticate explicitly with the bearer token; drop the session cookie so that
    # requests without headers really are anonymous.
    client.cookies.clear()
    return {"Authorization": f"Bearer {response.json()['token']}"}


def mastery_of(client: TestClient, headers: dict, skill_id: str) -> dict:
    skills = client.get("/api/v1/learner/mastery", headers=headers).json()["skills"]
    return next(s for s in skills if s["skill_id"] == skill_id)


def recommendations(client: TestClient, headers: dict, n: int = 5) -> list[dict]:
    return client.get(f"/api/v1/recommendation/next?n={n}", headers=headers).json()[
        "recommendations"
    ]


def create_user(client: TestClient, role: str = "student", level: str = "A1"):
    """Register an account and give it `role` the way an operator does (server-side, with
    banana_english.manage). Returns (Bearer headers, user id)."""
    from banana_english.domain.models import Role
    from banana_english.manage import set_role

    email = f"{role}-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse", "display_name": role.title()},
    )
    assert response.status_code == 201, response.text
    client.cookies.clear()
    user_id = response.json()["profile"]["learner_id"]
    if role != "student":
        set_role(client.app.state.container.uow_factory, email, Role(role))
    return {"Authorization": f"Bearer {response.json()['token']}"}, user_id
