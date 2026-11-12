"""Silent WAV of a length proportional to the text (tests / dev without a Piper voice)."""

from __future__ import annotations

import io
import wave

from banana_english.domain.interfaces.tts import TTSError, TTSProvider


class MockTTSProvider(TTSProvider):
    name = "mock-tts"

    def __init__(self, rate: int = 16_000, seconds_per_word: float = 0.3) -> None:
        self._rate = rate
        self._spw = seconds_per_word

    def synthesize(self, text: str) -> bytes:
        words = len(text.split())
        if not words:
            raise TTSError("nothing to say")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._rate)
            w.writeframes(b"\x00\x00" * int(self._rate * words * self._spw))
        return buf.getvalue()
