"""Synthesise listening audio from the transcripts in content/listening/lessons.json.

Voice: Piper en_US-ljspeech-medium (dataset: LJ Speech, public domain). Piper itself is
GPL and runs only here, offline; the generated audio is plain content.

    uv run --group content python scripts/build_listening_audio.py --voice-dir <dir>

The voice files (en_US-ljspeech-medium.onnx + .onnx.json) are downloaded from
https://huggingface.co/rhasspy/piper-voices if missing.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
import wave
from pathlib import Path

from piper import PiperVoice
from piper.config import SynthesisConfig

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "content/listening/lessons.json"
AUDIO_DIR = ROOT / "content/listening/audio"
VOICE = "en_US-ljspeech-medium"
VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/medium/"


def ensure_voice(voice_dir: Path) -> Path:
    voice_dir.mkdir(parents=True, exist_ok=True)
    for name in (f"{VOICE}.onnx", f"{VOICE}.onnx.json"):
        target = voice_dir / name
        if not target.exists():
            print(f"downloading {name}")
            with urllib.request.urlopen(VOICE_URL + name, timeout=300) as r:
                target.write_bytes(r.read())
    return voice_dir / f"{VOICE}.onnx"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice-dir", type=Path, default=Path.home() / ".cache/piper")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    voice = PiperVoice.load(str(ensure_voice(args.voice_dir)))
    # Slightly slower than default speech: these are learners.
    config = SynthesisConfig(length_scale=1.1)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    for lesson in json.loads(LESSONS.read_text(encoding="utf-8"))["lessons"]:
        out = AUDIO_DIR / lesson["audio_file"]
        if out.exists() and not args.force:
            continue
        with wave.open(str(out), "wb") as wav:
            voice.synthesize_wav(lesson["transcript"], wav, syn_config=config)
        with wave.open(str(out), "rb") as wav:
            seconds = wav.getnframes() / wav.getframerate()
        print(f"{out.name}: {seconds:.1f}s")


if __name__ == "__main__":
    main()
