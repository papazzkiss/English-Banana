from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from banana_english.domain.interfaces.infra import Cache

logger = logging.getLogger("banana_english.cache")


class MemoryCache(Cache):
    def __init__(self) -> None:
        self._data: dict[str, tuple[float | None, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return None
            expires, value = hit
            if expires is not None and expires < time.monotonic():
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        with self._lock:
            expires = time.monotonic() + ttl_seconds if ttl_seconds else None
            self._data[key] = (expires, value)


class RedisCache(Cache):
    """Redis-backed cache. Failures degrade to a cache miss; they never fail a request."""

    def __init__(self, url: str) -> None:
        import redis

        self._redis = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            raw = self._redis.get(key)
        except Exception as exc:
            logger.warning("redis get failed: %s", exc)
            return None
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        try:
            self._redis.set(key, json.dumps(value), ex=ttl_seconds)
        except Exception as exc:
            logger.warning("redis set failed: %s", exc)

    def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except Exception:
            return False
