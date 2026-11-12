from __future__ import annotations

import time

from banana_english.domain.interfaces.tts import TTSError, TTSProvider
from banana_english.infrastructure.observability.metrics import TTS_CALLS, TTS_LATENCY


class InstrumentedTTSProvider(TTSProvider):
    def __init__(self, inner: TTSProvider) -> None:
        self._inner = inner
        self.name = inner.name

    def synthesize(self, text: str) -> bytes:
        started = time.perf_counter()
        try:
            audio = self._inner.synthesize(text)
        except TTSError:
            TTS_CALLS.labels(self.name, "error").inc()
            raise
        TTS_LATENCY.labels(self.name).observe(time.perf_counter() - started)
        TTS_CALLS.labels(self.name, "ok").inc()
        return audio
