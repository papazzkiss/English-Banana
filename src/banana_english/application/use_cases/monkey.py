"""AI Monkey: free chat and speech-to-text for the chat's microphone. Separate from the
scripted conversation (Phase 8): no scenario, no grading, no mastery updates."""

from __future__ import annotations

import uuid
from pathlib import Path

from banana_english.application.services.language_policy import LanguagePreferences
from banana_english.application.services.monkey import MonkeyChat, MonkeyReply, MonkeyTurn
from banana_english.application.use_cases.common import (
    InvalidInputError,
    ProviderUnavailableError,
    UowFactory,
    require_learner,
)
from banana_english.application.use_cases.speaking import ALLOWED_SUFFIXES
from banana_english.domain.interfaces.llm import LLMProviderError
from banana_english.domain.interfaces.stt import STTError, STTProvider, Transcript
from banana_english.domain.interfaces.tts import TTSError, TTSProvider


class MonkeyConversation:
    def __init__(self, uow_factory: UowFactory, chat: MonkeyChat) -> None:
        self._uow_factory = uow_factory
        self._chat = chat

    def reply(
        self,
        learner_id: str,
        turns: list[MonkeyTurn],
        preferences: LanguagePreferences | None = None,
    ) -> MonkeyReply:
        if not turns or turns[-1].role != "learner":
            raise InvalidInputError("the last message must be the learner's")
        with self._uow_factory() as uow:
            _, profile = require_learner(uow, learner_id)
        try:  # outside the transaction: the model can take seconds
            return self._chat.reply(profile.current_level.value, turns, preferences)
        except LLMProviderError as exc:
            raise ProviderUnavailableError("AI Monkey cannot answer right now") from exc


class MonkeyTranscriber:
    """Transcribe one short voice message. The audio is deleted right after transcription."""

    def __init__(self, stt: STTProvider, upload_dir: Path, max_upload_bytes: int) -> None:
        self._stt = stt
        self._upload_dir = upload_dir
        self._max_bytes = max_upload_bytes

    def transcribe(self, audio: bytes, filename: str) -> Transcript:
        suffix = Path(filename or "audio.webm").suffix.lower() or ".webm"
        if suffix not in ALLOWED_SUFFIXES:
            raise InvalidInputError(f"unsupported audio type {suffix}")
        if not audio:
            raise InvalidInputError("empty audio upload")
        if len(audio) > self._max_bytes:
            raise InvalidInputError("audio upload too large")
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        path = self._upload_dir / f"monkey-{uuid.uuid4()}{suffix}"
        path.write_bytes(audio)
        try:
            return self._stt.transcribe(str(path))
        except STTError as exc:
            raise InvalidInputError(f"could not understand the audio: {exc}") from exc
        finally:
            path.unlink(missing_ok=True)


class MonkeyVoice:
    """AI Monkey's spoken replies, synthesised on the server (the same voice in every browser)."""

    def __init__(self, tts: TTSProvider) -> None:
        self._tts = tts

    def speak(self, text: str) -> bytes:
        try:
            return self._tts.synthesize(text.strip())
        except TTSError as exc:
            raise ProviderUnavailableError("AI Monkey's voice is unavailable right now") from exc
