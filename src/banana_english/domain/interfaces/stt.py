from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from banana_english.domain.services.fluency import Segment


@dataclass(frozen=True)
class Transcript:
    text: str
    segments: tuple[Segment, ...]
    duration_seconds: float
    language: str
    model: str


class STTError(Exception):
    """Audio could not be decoded or transcribed."""


class STTProvider(ABC):
    name: str = "stt"

    @abstractmethod
    def transcribe(self, audio_path: str) -> Transcript:
        """Transcribe English speech. Raise STTError on failure."""
