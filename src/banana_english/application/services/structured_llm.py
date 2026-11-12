"""One way to get structured output from an LLM: call -> strict parse -> retry -> cache.

The cache (Redis in production) makes scoring repeatable: the same prompt version, model,
item and normalised answer always yields the same verdict, so identical answers cannot drift
between days. Cache keys include the prompt version, so a prompt change starts fresh.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from banana_english.application.services.llm_contracts import (
    InvalidLLMOutputError,
    parse_llm_json,
)
from banana_english.domain.interfaces.assessment import AssessmentUnavailableError
from banana_english.domain.interfaces.infra import Cache
from banana_english.domain.interfaces.llm import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMTimeoutError,
)

M = TypeVar("M", bound=BaseModel)

CACHE_TTL_SECONDS = 60 * 60 * 24 * 90
logger = logging.getLogger("banana_english.llm")


def cache_key(task: str, prompt_version: str, provider: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]
    return f"llm:{task}:{prompt_version}:{provider}:{digest}"


class StructuredLLM:
    def __init__(self, llm: LLMProvider, cache: Cache | None = None, max_retries: int = 1) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.llm = llm
        self._cache = cache
        self._max_retries = max_retries

    def run(
        self,
        request: LLMRequest,
        model: type[M],
        key: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[M, str]:
        """Return (validated object, model name). Raise AssessmentUnavailableError.
        `context` is passed to schema validation (e.g. the learner answer for grounding)."""
        if key and self._cache and (hit := self._cache.get(key)):
            try:
                verdict = model.model_validate(hit["data"], context=context), hit["model"]
            except Exception:  # stale/corrupt cache entry: fall through to the model
                pass
            else:
                logger.info("llm_cache_hit task=%s model=%s", request.task, hit["model"])
                return verdict

        failures: list[str] = []
        attempts = 1 + self._max_retries
        for attempt in range(1, attempts + 1):
            if failures:
                logger.warning(
                    "llm_retry task=%s attempt=%d/%d after: %s",
                    request.task,
                    attempt,
                    attempts,
                    failures[-1],
                )
            try:
                response = self.llm.complete(request)
            except LLMTimeoutError as exc:  # the model is saturated: a retry doubles the wait
                failures.append(f"provider error: {exc}")
                break
            except LLMProviderError as exc:
                failures.append(f"provider error: {exc}")
                continue
            try:
                parsed = parse_llm_json(response.text, model, context)
            except InvalidLLMOutputError as exc:
                failures.append(str(exc))
                continue
            # a fallback model's verdict is used once, never cached as the production verdict
            if key and self._cache and not response.fallback:
                self._cache.set(
                    key,
                    {"data": parsed.model_dump(mode="json"), "model": response.model},
                    CACHE_TTL_SECONDS,
                )
            return parsed, response.model
        raise AssessmentUnavailableError(" | ".join(failures), attempts=len(failures))
