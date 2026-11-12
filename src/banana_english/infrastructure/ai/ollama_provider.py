"""Qwen3 via Ollama (local). Uses /api/chat with JSON-schema structured output.

Thinking per request (Qwen3's hybrid mode): a request with `think=True` (explaining a mistake,
judging an answer) lets the model reason first, with its own token budget on top of the
answer's. Ollama returns the reasoning separately (`message.thinking`); it is logged by size
only and never returned, so learners only ever see the final answer. Every other request runs
with `think: false` (Qwen3 non-thinking mode). Sampling follows Qwen's recommendation for each
mode (thinking: top_p 0.95, never greedy; non-thinking: top_p 0.8), top_k 20.

The model, context length, keep-alive, timeout and the optional temperature / max-token
overrides all come from Settings (BANANA_OLLAMA_MODEL, BANANA_LLM_*); nothing is hard-coded here.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

import httpx

from banana_english.domain.interfaces.llm import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)

logger = logging.getLogger("banana_english.llm")
_SETUP_HINT = "build it with scripts/setup_ollama_model.sh (or `ollama pull` a library model)"


THINK_MIN_TEMPERATURE = 0.6  # Qwen3: greedy decoding in thinking mode loops and repeats


def chat_body(
    model: str,
    request: LLMRequest,
    keep_alive: str,
    options: Mapping[str, Any] | None = None,
    *,
    think: bool = False,
    think_budget: int = 0,
) -> dict:
    """The /api/chat body for a request. Shared with the model benchmark
    (banana_english.benchmark), so it measures exactly what production sends.
    `options` are provider-level settings (context length, overrides) laid over the request's.
    `think`: reason first; the reply may then use `think_budget` more tokens."""
    temperature = request.temperature
    if think:
        temperature = max(temperature, THINK_MIN_TEMPERATURE)
    body: dict = {
        "model": model,
        "stream": False,
        "think": think,
        "keep_alive": keep_alive,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "options": {
            "temperature": temperature,
            "top_p": 0.95 if think else 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "num_predict": request.max_output_tokens + (think_budget if think else 0),
            **(options or {}),
        },
    }
    if request.response_schema is not None:
        body["format"] = dict(request.response_schema)
    return body


def _ms(ns: Any) -> float | None:
    return round(ns / 1e6, 1) if isinstance(ns, int | float) and ns > 0 else None


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 120.0,
        keep_alive: str = "30m",
        *,
        num_ctx: int | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        thinking: bool = True,
        think_budget: int = 1024,
        transport: httpx.BaseTransport | None = None,  # tests
    ) -> None:
        """num_ctx: context window sent with every request (None = the model's default).
        temperature: replaces every task's temperature (None = each task keeps its own).
        max_output_tokens: upper bound on every reply (None = each task's own limit).
        thinking: honour requests that ask to think (False = never think).
        think_budget: reasoning tokens allowed on top of a thinking request's answer."""
        self.model = model
        self.name = f"ollama:{model}"
        self.base_url = base_url.rstrip("/")
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self.timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self.thinking = thinking
        self.think_budget = think_budget
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout_seconds, transport=transport
        )

    def _options(self, request: LLMRequest) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        if self._temperature is not None:
            options["temperature"] = self._temperature
        if self._max_output_tokens:
            options["num_predict"] = min(request.max_output_tokens, self._max_output_tokens)
        return options

    def complete(self, request: LLMRequest) -> LLMResponse:
        think = bool(request.think and self.thinking)
        data = self._chat(request, think)
        text = (data.get("message") or {}).get("content")
        if think and not (text or "").strip():
            # the reasoning used the whole budget before any answer: answer without thinking
            logger.warning(
                "llm_think_exhausted task=%s model=%s thinking_chars=%s; retrying without",
                request.task,
                self.model,
                len((data.get("message") or {}).get("thinking") or ""),
            )
            think = False
            data = self._chat(request, think)
            text = (data.get("message") or {}).get("content")
        return self._response(data, text, think)

    def _chat(self, request: LLMRequest, think: bool) -> dict:
        body = chat_body(
            self.model,
            request,
            self.keep_alive,
            self._options(request),
            think=think,
            think_budget=self.think_budget,
        )
        try:
            response = self._client.post("/api/chat", json=body)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"ollama: {self.model} did not answer within {self.timeout_seconds:.0f}s"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(self._status_error(exc.response)) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMProviderError(f"ollama request failed: {exc}") from exc
        return data

    def _response(self, data: dict, text: Any, think: bool) -> LLMResponse:
        if not isinstance(text, str):
            raise LLMProviderError("ollama response has no message content")
        eval_count, eval_ns = data.get("eval_count"), data.get("eval_duration")
        stats = {
            k: v
            for k, v in (
                ("load_ms", _ms(data.get("load_duration"))),
                ("prompt_eval_ms", _ms(data.get("prompt_eval_duration"))),
                ("eval_ms", _ms(eval_ns)),
                ("total_ms", _ms(data.get("total_duration"))),
                ("think", 1.0 if think else 0.0),
                ("thinking_chars", float(len((data.get("message") or {}).get("thinking") or ""))),
            )
            if v is not None
        }
        return LLMResponse(
            text=text,
            model=data.get("model", self.model),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=eval_count,
            tokens_per_second=round(eval_count / eval_ns * 1e9, 2)
            if eval_count and eval_ns
            else None,
            stats=stats,
        )

    def _status_error(self, response: httpx.Response) -> str:
        try:
            detail = response.json().get("error") or response.text
        except ValueError:
            detail = response.text
        message = f"ollama {response.status_code} for model {self.model}: {detail}"
        if response.status_code == 404:
            message += f" ({_SETUP_HINT})"
        return message

    def ping(self) -> bool:
        try:
            return self._client.get("/api/tags", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False

    def warm_up(self) -> None:
        """Load the model now (with the same context size the requests use, so Ollama does not
        reload it on the first request) and log whether it is available."""
        body: dict[str, Any] = {"model": self.model, "keep_alive": self.keep_alive}
        if self.num_ctx:
            body["options"] = {"num_ctx": self.num_ctx}
        started = time.perf_counter()
        try:
            response = self._client.post("/api/generate", json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("llm_unavailable %s", self._status_error(exc.response))
        except httpx.HTTPError as exc:
            logger.error(
                "llm_unavailable model=%s ollama=%s not reachable: %s",
                self.model,
                self.base_url,
                exc,
            )
        else:
            logger.info(
                "llm_ready model=%s num_ctx=%s keep_alive=%s load_s=%.1f",
                self.model,
                self.num_ctx or "model default",
                self.keep_alive,
                time.perf_counter() - started,
            )
