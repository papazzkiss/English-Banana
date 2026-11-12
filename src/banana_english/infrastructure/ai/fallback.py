"""Primary model, then an explicitly configured fallback model (BANANA_LLM_FALLBACK_MODEL).

Only used when a fallback is configured: without one, the production model never changes and a
failure reaches the caller (which degrades as before: 503 / "assessment unavailable").

* Falls back when the primary is unavailable (model missing, failed to load, error status).
* Never on a timeout: the runtime is busy, and loading a second model would make it worse.
* Every fallback is logged (WARNING) and counted; the response carries `fallback=True` and the
  model that actually answered, so audit rows and cached verdicts are never attributed to the
  primary model.
"""

from __future__ import annotations

import dataclasses
import logging

from banana_english.domain.interfaces.llm import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)
from banana_english.infrastructure.observability.metrics import LLM_FALLBACKS

logger = logging.getLogger("banana_english.llm")


class FallbackLLMProvider(LLMProvider):
    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name  # cache keys and metrics stay under the production model

    def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            return self.primary.complete(request)
        except LLMTimeoutError:
            raise
        except LLMProviderError as exc:
            logger.warning(
                "llm_fallback task=%s primary=%s fallback=%s reason=%s",
                request.task,
                self.primary.name,
                self.fallback.name,
                exc,
            )
            LLM_FALLBACKS.labels(
                primary=self.primary.name, fallback=self.fallback.name, task=request.task
            ).inc()
            try:
                response = self.fallback.complete(request)
            except LLMProviderError as fallback_exc:
                raise LLMProviderError(
                    f"{exc}; fallback {self.fallback.name} failed too: {fallback_exc}"
                ) from fallback_exc
            return dataclasses.replace(response, fallback=True)

    def warm_up(self) -> None:
        self.primary.warm_up()  # the fallback loads only if it is ever needed
