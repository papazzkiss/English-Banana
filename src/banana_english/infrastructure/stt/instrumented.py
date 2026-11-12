from __future__ import annotations

import logging
import time

from banana_english.domain.interfaces.stt import STTError, STTProvider, Transcript
from banana_english.infrastructure.observability.context import current_request_id
from banana_english.infrastructure.observability.metrics import (
    STT_AUDIO_SECONDS,
    STT_CALLS,
    STT_LATENCY,
)

logger = logging.getLogger("banana_english.stt")


class InstrumentedSTTProvider(STTProvider):
    def __init__(self, inner: STTProvider) -> None:
        self._inner = inner
        self.name = inner.name

    def transcribe(self, audio_path: str) -> Transcript:
        started = time.perf_counter()
        try:
            transcript = self._inner.transcribe(audio_path)
        except STTError:
            STT_CALLS.labels(provider=self.name, outcome="error").inc()
            raise
        finally:
            STT_LATENCY.labels(provider=self.name).observe(time.perf_counter() - started)
        STT_CALLS.labels(provider=self.name, outcome="ok").inc()
        STT_AUDIO_SECONDS.labels(provider=self.name).inc(transcript.duration_seconds)
        logger.info(
            "stt_call provider=%s audio_s=%.1f latency_ms=%.0f request_id=%s",
            self.name,
            transcript.duration_seconds,
            (time.perf_counter() - started) * 1000,
            current_request_id(),
        )
        return transcript
