"""AI Monkey: free conversation with a friendly monkey, who is also a bilingual (English and
Vietnamese) tutor. Plain-text replies; nothing is graded, so mastery is never touched.

The language of each reply comes from a LanguagePolicy (language_policy.py): the learner's
preferences, natural commands in their latest message, and the language they wrote in."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from banana_english.application.services.conversation import sanitize_reply
from banana_english.application.services.language_policy import (
    LanguagePreferences,
    TurnPolicy,
    parse_message,
    replay_preferences,
    resolve,
)
from banana_english.application.services.prompts import MONKEY_CHAT_VERSION, monkey_chat_system
from banana_english.domain.interfaces.llm import (
    LLMMessage,
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMTimeoutError,
)

logger = logging.getLogger("banana_english.llm")
MAX_HISTORY = 12  # turns sent to the model; older turns are dropped
HISTORY_STEP = 6  # the window moves 6 turns at a time (see recent_turns)
CHAT_TOKENS, DETAILED_TOKENS = 200, 400  # explanations (often in Vietnamese) need more room
CHAT_CHARS, DETAILED_CHARS = 400, 900  # stays under the API's 1000-character message limit
_LABEL = re.compile(r"^\s*(ai\s*monkey|monkey)\s*:\s*", re.I)
_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿️]")


@dataclass(frozen=True)
class MonkeyTurn:
    role: str  # "learner" | "monkey"
    text: str


@dataclass(frozen=True)
class MonkeyReply:
    text: str
    model: str
    prompt_version: str = MONKEY_CHAT_VERSION
    preferences: LanguagePreferences = LanguagePreferences()  # after this message's commands
    policy: TurnPolicy | None = None


_MARKDOWN = re.compile(r"\*\*|__|`")
# A "tip" that only says the learner was right corrects nothing: drop it.
_EMPTY_TIP = re.compile(
    r"\s*\(Tip:[^)]*(\bis (correct|fine|right)\b|\bare correct\b|no change|"
    r"đúng rồi|không cần sửa|là đúng)[^)]*\)",
    re.I,
)


def clean_reply(raw: str, max_chars: int = CHAT_CHARS) -> str:
    """The model's text as the learner sees and hears it (shared with the model benchmark):
    no role label, emoji or markdown emphasis (the reply may be read aloud)."""
    text = _MARKDOWN.sub("", _EMOJI.sub("", _LABEL.sub("", raw)))
    return sanitize_reply(_EMPTY_TIP.sub("", text), max_chars)


def recent_turns(turns: list[MonkeyTurn]) -> list[MonkeyTurn]:
    """At most MAX_HISTORY turns, dropping old ones HISTORY_STEP at a time. A window that slid
    by one turn per message changed the start of the prompt every time, so Ollama re-read the
    whole history on every turn past the 12th (measured: 12-20 s of prompt evaluation on CPU);
    moving in steps keeps the cached prefix for 3 exchanges. Starts on an even index, so the
    window still opens with a learner turn."""
    overflow = len(turns) - MAX_HISTORY
    if overflow <= 0:
        return turns
    return turns[-(-overflow // HISTORY_STEP) * HISTORY_STEP :]


def _untrusted(text: str) -> str:
    # the learner cannot forge the app's note
    return text.replace("[App settings", "(App settings")


class MonkeyChat:
    def __init__(self, llm: LLMProvider, max_retries: int = 1) -> None:
        self._llm = llm
        self._max_retries = max_retries

    def reply(
        self,
        cefr_level: str,
        turns: list[MonkeyTurn],
        preferences: LanguagePreferences | None = None,
    ) -> MonkeyReply:
        """`preferences`: what the client kept from earlier turns. None (an older client):
        rebuilt from the commands in the history, so "from now on…" still lasts."""
        latest = turns[-1].text if turns else ""
        if preferences is None:
            preferences = replay_preferences(t.text for t in turns[:-1] if t.role == "learner")
        parsed = parse_message(latest, preferences)
        policy = resolve(parsed, latest)

        messages = [LLMMessage("system", monkey_chat_system(cefr_level))]
        recent = recent_turns(turns)
        note = policy.instruction()
        for i, t in enumerate(recent):
            content = _untrusted(t.text) if t.role == "learner" else t.text
            if i == len(recent) - 1 and t.role == "learner" and note:
                content = f"{content}\n\n{note}"
            messages.append(LLMMessage("assistant" if t.role == "monkey" else "user", content))
        request = LLMRequest(
            task="monkey_chat",
            prompt_version=MONKEY_CHAT_VERSION,
            messages=tuple(messages),
            temperature=0.8,
            max_output_tokens=DETAILED_TOKENS if policy.detailed else CHAT_TOKENS,
            think=policy.detailed,  # an explanation reasons first; small talk answers at once
            context={
                "turn": len(turns),
                "last": latest,
                "intent": policy.intent,
                "explanation_language": policy.explanation_language,
            },
        )
        max_chars = DETAILED_CHARS if policy.detailed else CHAT_CHARS
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
                response = self._llm.complete(request)
            except LLMTimeoutError as exc:  # the model is saturated: a retry doubles the wait
                last_error = str(exc)
                break
            except LLMProviderError as exc:
                last_error = str(exc)
                continue
            text = clean_reply(response.text, max_chars)
            if text:
                return MonkeyReply(
                    text, response.model, preferences=parsed.preferences, policy=policy
                )
        raise LLMProviderError(f"monkey reply failed: {last_error}")
