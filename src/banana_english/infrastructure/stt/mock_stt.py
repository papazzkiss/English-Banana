from __future__ import annotations

from pathlib import Path

from banana_english.domain.interfaces.stt import STTError, STTProvider, Transcript
from banana_english.domain.services.fluency import Segment


class MockSTTProvider(STTProvider):
    """Returns a fixed transcript (tests / dev without a Whisper model).

    If a sidecar file `<audio>.txt` exists its content is used instead, which lets tests
    upload "audio" with a known transcript.
    """

    name = "mock-stt"

    def __init__(
        self,
        text: str = "Last weekend I go to the beach with my friends and we swim.",
        words_per_second: float = 2.2,
    ) -> None:
        self._text = text
        self._wps = words_per_second

    def transcribe(self, audio_path: str) -> Transcript:
        path = Path(audio_path)
        if not path.exists() or path.stat().st_size == 0:
            raise STTError("empty or missing audio")
        sidecar = path.with_name(path.name + ".txt")
        text = sidecar.read_text().strip() if sidecar.exists() else self._text
        seconds = max(1.0, len(text.split()) / self._wps)
        return Transcript(
            text=text,
            segments=(Segment(0.0, seconds, text),),
            duration_seconds=seconds,
            language="en",
            model="mock-stt",
        )
