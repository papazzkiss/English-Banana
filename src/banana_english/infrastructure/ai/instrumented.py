"""Decorator around any LLMProvider: Prometheus metrics + llm_calls audit log + request id.

Business code never sees this; the container wraps the configured provider with it.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from datetime import UTC, datetime

from banana_english.domain.interfaces.llm import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
)
from banana_english.domain.interfaces.repositories import LLMCallLog
from banana_english.infrastructure.observability.context import current_request_id
from banana_english.infrastructure.observability.metrics import (
    LLM_CALLS,
    LLM_COST,
    LLM_LATENCY,
    LLM_TOKENS,
    LLM_TOKENS_PER_SECOND,
)

logger = logging.getLogger("banana_english.llm")
MAX_LOGGED_RESPONSE = 4000
# (request id, LLM calls so far in it): "call_n" in the log shows how many inferences one API
# request made (a normal chat message must make exactly one).
_calls_in_request: ContextVar[tuple[str | None, int]] = ContextVar("llm_calls", default=(None, 0))


def _next_call_number(request_id: str | None) -> int:
    previous_id, n = _calls_in_request.get()
    n = n + 1 if request_id is not None and previous_id == request_id else 1
    _calls_in_request.set((request_id, n))
    return n


class InstrumentedLLMProvider(LLMProvider):
    def __init__(
        self,
        inner: LLMProvider,
        call_log: LLMCallLog | None = None,
        cost_per_1k_tokens: float = 0.0,
    ) -> None:
        self._inner = inner
        self._log = call_log
        self._cost_per_1k = cost_per_1k_tokens
        self.name = inner.name

    def warm_up(self) -> None:
        self._inner.warm_up()

    def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        response: LLMResponse | None = None
        error: str | None = None
        try:
            response = self._inner.complete(request)
            return response
        except LLMProviderError as exc:
            error = str(exc)
            raise
        finally:
            elapsed = time.perf_counter() - started
            labels = {"provider": self.name, "task": request.task}
            LLM_LATENCY.labels(**labels).observe(elapsed)
            LLM_CALLS.labels(**labels, outcome="ok" if error is None else "error").inc()
            tokens = 0
            if response is not None:
                for kind, n in (
                    ("input", response.input_tokens),
                    ("output", response.output_tokens),
                ):
                    if n:
                        LLM_TOKENS.labels(**labels, kind=kind).inc(n)
                        tokens += n
                LLM_COST.labels(**labels).inc(tokens / 1000 * self._cost_per_1k)
                if response.tokens_per_second:
                    LLM_TOKENS_PER_SECOND.labels(**labels).observe(response.tokens_per_second)
            request_id = current_request_id()
            call_n = _next_call_number(request_id)
            stats = response.stats if response else {}
            # one line per call: which model really answered, how long it took, and why it failed
            logger.log(
                logging.INFO if error is None else logging.WARNING,
                "llm_call task=%s prompt=%s provider=%s model=%s latency_ms=%.0f input_tokens=%s "
                "output_tokens=%s tok_s=%s load_ms=%s prompt_eval_ms=%s eval_ms=%s think=%s "
                "thinking_chars=%s fallback=%s ok=%s error=%s call_n=%d request_id=%s",
                request.task,
                request.prompt_version,
                self.name,
                response.model if response else None,
                elapsed * 1000,
                response.input_tokens if response else None,
                response.output_tokens if response else None,
                response.tokens_per_second if response else None,
                stats.get("load_ms"),
                stats.get("prompt_eval_ms"),
                stats.get("eval_ms"),
                bool(stats.get("think")) if stats else request.think,
                int(stats["thinking_chars"]) if "thinking_chars" in stats else None,
                response.fallback if response else False,
                error is None,
                error,
                call_n,
                request_id,
            )
            if self._log is not None:
                try:
                    self._log.record(
                        {
                            "request_id": request_id,
                            "task": request.task,
                            "prompt_version": request.prompt_version,
                            "provider": self.name,
                            "model": response.model if response else None,
                            "latency_ms": round(elapsed * 1000, 1),
                            "input_tokens": response.input_tokens if response else None,
                            "output_tokens": response.output_tokens if response else None,
                            "ok": error is None,
                            "error": error,
                            "response_text": response.text[:MAX_LOGGED_RESPONSE]
                            if response
                            else None,
                            "created_at": datetime.now(UTC),
                        }
                    )
                except Exception:  # auditing must never break a learner request
                    logger.exception("failed to write llm_calls audit row")
