from __future__ import annotations

from abc import ABC, abstractmethod


class TTSError(Exception):
    """Speech could not be synthesised (model missing, engine failure)."""


class TTSProvider(ABC):
    name: str = "tts"

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Return a complete WAV file (16-bit PCM) speaking `text`. Raise TTSError on failure."""
