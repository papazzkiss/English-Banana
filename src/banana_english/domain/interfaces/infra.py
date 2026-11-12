"""Small infrastructure ports: clock, key-value cache, background jobs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime: ...


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


class Cache(ABC):
    """JSON-serialisable key-value cache. Used to make LLM verdicts repeatable:
    the same (prompt version, model, item, normalised answer) always gets the same score."""

    @abstractmethod
    def get(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def set(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None: ...


class JobRunner(ABC):
    """Runs slow work (STT + LLM) off the request path."""

    @abstractmethod
    def submit(self, fn: Callable[[], None]) -> None: ...
