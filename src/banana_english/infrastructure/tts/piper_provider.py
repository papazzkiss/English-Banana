"""Server-side speech for AI Monkey with Piper (offline neural TTS, CPU-friendly).

Browsers cannot be relied on to speak: Chromium-based browsers on Linux, such as Brave, have
no speechSynthesis voices at all. The voice (~60 MB) is downloaded once into `model_dir` and
loaded lazily on first use.
"""

from __future__ import annotations

import io
import shutil
import threading
import urllib.request
import wave
from pathlib import Path

from banana_english.domain.interfaces.tts import TTSError, TTSProvider

VOICES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
DOWNLOAD_TIMEOUT_S = 60


def _voice_path(voice: str) -> str:
    """en_US-ljspeech-medium -> en/en_US/ljspeech/medium/."""
    locale, name, quality = voice.split("-")
    return f"{locale.split('_')[0]}/{locale}/{name}/{quality}/"


class PiperTTSProvider(TTSProvider):
    name = "piper"

    def __init__(self, voice: str, model_dir: Path, length_scale: float = 0.95) -> None:
        self._voice_name = voice
        self._dir = Path(model_dir)
        self._length_scale = length_scale
        self._voice = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._voice is None:
                from piper import PiperVoice  # dependency group "speech"

                self._dir.mkdir(parents=True, exist_ok=True)
                for suffix in (".onnx", ".onnx.json"):
                    target = self._dir / f"{self._voice_name}{suffix}"
                    if not target.exists():
                        url = VOICES_URL + _voice_path(self._voice_name) + target.name
                        tmp = target.with_suffix(target.suffix + ".part")
                        # A timeout: a stalled download must not hold the lock forever.
                        with (
                            urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_S) as src,  # noqa: S310
                            tmp.open("wb") as dst,
                        ):
                            shutil.copyfileobj(src, dst)
                        tmp.rename(target)
                self._voice = PiperVoice.load(str(self._dir / f"{self._voice_name}.onnx"))
        return self._voice

    def synthesize(self, text: str) -> bytes:
        if not text.strip():
            raise TTSError("nothing to say")
        try:
            from piper import SynthesisConfig

            voice = self._load()
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                voice.synthesize_wav(
                    text, w, syn_config=SynthesisConfig(length_scale=self._length_scale)
                )
            data = buf.getvalue()
        except TTSError:
            raise
        except Exception as exc:  # download, onnxruntime or phonemizer failures
            raise TTSError(f"{type(exc).__name__}: {exc}") from exc
        if len(data) <= 44:  # a WAV header and no audio
            raise TTSError("empty audio")
        return data
