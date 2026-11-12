"""Scenario role-play (Phase 8). Replies are plain text; corrections happen AFTER the
conversation (batch assessment), never mid-reply."""

from __future__ import annotations

import logging
import re

from banana_english.application.services.llm_contracts import strip_reasoning
from banana_english.application.services.prompts import (
    CONVERSATION_REPLY_VERSION,
    conversation_system,
)
from banana_english.domain.interfaces.llm import (
    LLMMessage,
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMTimeoutError,
)
from banana_english.domain.models import ConversationScenario, ConversationTurn

logger = logging.getLogger("banana_english.llm")
MAX_REPLY_CHARS = 400
_LABEL = re.compile(r"^\s*(assistant|waiter|receptionist|colleague|local|ai)\s*:\s*", re.I)


def sanitize_reply(raw: str, max_chars: int = MAX_REPLY_CHARS) -> str:
    text = strip_reasoning(raw)
    text = _LABEL.sub("", text).strip()
    # a reply wrapped in quotes as a whole loses them; one that starts or ends with a quoted
    # word or example ("Since" is for...) keeps them
    if len(text) > 1 and text[0] == text[-1] == '"' and '"' not in text[1:-1]:
        text = text[1:-1].strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_chars:
        cut = text[:max_chars]
        text = cut[: max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! ")) + 1] or cut
    return text


class ConversationPartner:
    def __init__(self, llm: LLMProvider, max_retries: int = 1) -> None:
        self._llm = llm
        self._max_retries = max_retries

    def reply(self, scenario: ConversationScenario, turns: list[ConversationTurn]) -> str:
        messages = [LLMMessage("system", conversation_system(scenario))]
        for t in turns:
            messages.append(LLMMessage("assistant" if t.role == "assistant" else "user", t.text))
        request = LLMRequest(
            task="conversation_reply",
            prompt_version=CONVERSATION_REPLY_VERSION,
            messages=tuple(messages),
            temperature=0.7,
            max_output_tokens=160,
            context={"scenario_id": scenario.id, "turn": len(turns)},
        )
        last_error = "empty reply"
        attempts = 1 + self._max_retries
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                logger.warning(
                    "llm_retry task=%s attempt=%d/%d after: %s",
                    request.task,
                    attempt,
                    attempts,
                    last_error,
                )
            try:
                text = sanitize_reply(self._llm.complete(request).text)
            except LLMTimeoutError as exc:  # the model is saturated: a retry doubles the wait
                last_error = str(exc)
                break
            except LLMProviderError as exc:
                last_error = str(exc)
                continue
            if text:
                return text
        raise LLMProviderError(f"conversation reply failed: {last_error}")
