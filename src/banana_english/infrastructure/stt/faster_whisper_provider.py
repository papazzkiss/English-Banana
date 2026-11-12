"""Whisper STT via faster-whisper (CTranslate2, CPU-friendly, no PyTorch).

Decoding uses PyAV (bundled FFmpeg), so browser uploads (webm/opus, ogg, mp4) and wav work.
The model is loaded lazily on first use and cached for the process lifetime.
"""

from __future__ import annotations

import threading

from banana_english.domain.interfaces.stt import STTError, STTProvider, Transcript
from banana_english.domain.services.fluency import Segment


class FasterWhisperProvider(STTProvider):
    name = "faster-whisper"

    def __init__(self, model_size: str = "base.en", compute_type: str = "int8") -> None:
        self._model_size = model_size
        self._compute_type = compute_type
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel  # optional dependency group "speech"

                self._model = WhisperModel(
                    self._model_size, device="cpu", compute_type=self._compute_type
                )
        return self._model

    def transcribe(self, audio_path: str) -> Transcript:
        try:
            segments, info = self._load().transcribe(
                audio_path, language="en", beam_size=5, vad_filter=True
            )
            parts = [Segment(s.start, s.end, s.text.strip()) for s in segments]
        except Exception as exc:  # decoding errors come from several libraries
            raise STTError(f"transcription failed: {exc}") from exc
        return Transcript(
            text=" ".join(p.text for p in parts).strip(),
            segments=tuple(parts),
            duration_seconds=round(float(info.duration), 2),
            language=info.language,
            model=f"whisper-{self._model_size}",
        )
