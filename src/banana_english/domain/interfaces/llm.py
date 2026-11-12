"""LLM provider port.

Business logic depends on this interface only — never on Qwen, Ollama or any SDK.
A provider is a transport: it returns raw text and makes no correctness promises.
Everything it returns is untrusted until validated by the caller.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMRequest:
    task: str  # "grammar_assessment", "listening_assessment", "conversation_reply", ...
    messages: tuple[LLMMessage, ...]
    prompt_version: str
    response_schema: Mapping[str, Any] | None = None  # JSON Schema; None = plain text reply
    temperature: float = 0.0
    max_output_tokens: int = 512  # the answer's budget (reasoning, if any, gets its own)
    # The task benefits from step-by-step reasoning before answering (explaining a mistake,
    # judging an answer). Providers that support it think first and return only the final
    # answer; the reasoning is never shown to the learner.
    think: bool = False
    # Structured inputs the prompt was rendered from. Real providers ignore it; it exists
    # for tracing and for deterministic test doubles.
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str  # the model that actually answered (may be a configured fallback)
    input_tokens: int | None = None
    output_tokens: int | None = None
    tokens_per_second: float | None = None  # output tokens / generation time, if reported
    fallback: bool = False  # answered by the configured fallback model, not the primary
    stats: Mapping[str, float] = field(default_factory=dict)  # runtime timings (ms), for logs


class LLMProviderError(Exception):
    """Transport-level failure: timeout, connection error, provider error status."""


class LLMTimeoutError(LLMProviderError):
    """The model did not answer within the timeout. Retrying at once rarely helps: the runtime
    is saturated (a CPU-bound model), and a retry doubles the learner's wait."""


class LLMProvider(ABC):
    name: str = "llm"

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return raw model output. Raise LLMProviderError on transport failure."""

    def warm_up(self) -> None:  # noqa: B027 - optional hook, a no-op for most providers
        """Load the model ahead of the first request (optional; never raises)."""

    def generate(self, prompt: str, system: str | None = None, *, task: str = "adhoc") -> str:
        """Convenience wrapper for one-off prompts (scripts, experiments)."""
        messages = ([LLMMessage("system", system)] if system else []) + [LLMMessage("user", prompt)]
        return self.complete(LLMRequest(task, tuple(messages), prompt_version="adhoc")).text
