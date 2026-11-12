"""Listening recordings: synthesise every listening passage with Piper (the voice AI Monkey
uses), encode Ogg/Opus mono 16 kbit/s, and write the durations back into the bank.

Resumable: existing files are kept. A passage whose audio cannot be made is set to draft, so
no question ever points at a missing recording.
"""

from __future__ import annotations

import io
import os
import re
import wave
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from banana_english.contentbank.schema import PassageRecord
from banana_english.contentbank.store import BANK_DIR, iter_records, write_skill
from banana_english.domain.models.bank import BankStatus

AUDIO_DIR = BANK_DIR / "audio"
VOICE = "en_US-ljspeech-medium"
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def speakable(text: str) -> str:
    """Text as it should be read: 8:30 -> 8 30, 14:00 -> 14 o'clock."""

    def time(m: re.Match) -> str:
        h, mins = m.group(1), m.group(2)
        return f"{h} o'clock" if mins == "00" else f"{h} {mins}"

    return _TIME.sub(time, text)


_TTS = None
WORKERS = 3


def _limit_onnx_threads() -> None:
    """Each worker gets its share of the cores. ONNX Runtime otherwise starts one thread per
    core in every worker, and three workers fighting over the cores ran 50 times slower
    (measured: 68 s for a 35 s paragraph). Only this offline build process is affected."""
    import onnxruntime

    per_worker = max(1, (os.cpu_count() or WORKERS) // WORKERS)
    make_options = onnxruntime.SessionOptions

    def options():
        o = make_options()
        o.intra_op_num_threads = per_worker
        o.inter_op_num_threads = 1
        return o

    onnxruntime.SessionOptions = options


def _synth(job: tuple[str, str]) -> tuple[str, float | None, str | None]:
    """(relative path, text) -> (path, duration seconds, error)."""
    global _TTS
    path, text = job
    target = AUDIO_DIR / path
    try:
        if target.exists() and target.stat().st_size > 0:
            return path, _duration(target), None
        if _TTS is None:
            from banana_english.infrastructure.tts.piper_provider import PiperTTSProvider

            _limit_onnx_threads()

            _TTS = PiperTTSProvider(
                VOICE, Path(os.environ.get("PIPER_DIR", Path.home() / ".cache/piper"))
            )
        wav = _TTS.synthesize(speakable(text))
        target.parent.mkdir(parents=True, exist_ok=True)
        _encode(wav, target)
        return path, _duration(target), None
    except Exception as exc:  # noqa: BLE001 - reported, the passage becomes a draft
        return path, None, str(exc)[:200]


def _encode(wav: bytes, target: Path) -> None:
    import av

    tmp = target.with_suffix(".part")
    with wave.open(io.BytesIO(wav)) as w:
        rate, frames = w.getframerate(), w.readframes(w.getnframes())
    import numpy as np

    samples = np.frombuffer(frames, dtype=np.int16).reshape(1, -1)
    with av.open(str(tmp), "w", format="ogg") as out:
        stream = out.add_stream("libopus", rate=24000, layout="mono")
        stream.bit_rate = 16000
        frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
        frame.sample_rate = rate
        resampler = av.AudioResampler(format="s16", layout="mono", rate=24000)
        for f in resampler.resample(frame) + resampler.resample(None):
            for packet in stream.encode(f):
                out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    tmp.replace(target)


def _duration(path: Path) -> float | None:
    import av

    with av.open(str(path)) as f:
        stream = f.streams.audio[0]
        if stream.duration and stream.time_base:
            return round(float(stream.duration * stream.time_base), 2)
        return round(f.duration / 1_000_000, 2) if f.duration else None


def synthesize_all(log: Callable[[str], None] = print, workers: int = WORKERS) -> dict:
    records = list(iter_records(BANK_DIR))
    passages = [r for r in records if isinstance(r, PassageRecord) and r.skill == "listening"]
    questions = [r for r in records if not isinstance(r, PassageRecord) and r.skill == "listening"]
    jobs = [(p.audio, p.text) for p in passages if p.audio]
    results: dict[str, tuple[float | None, str | None]] = {}
    with ProcessPoolExecutor(workers) as pool:
        for i, (path, dur, err) in enumerate(pool.map(_synth, jobs, chunksize=8), start=1):
            results[path] = (dur, err)
            if i % 500 == 0:
                log(f"  audio {i:,}/{len(jobs):,}")
    updated = []
    broken = 0
    for p in passages:
        dur, err = results.get(p.audio or "", (None, "no audio path"))
        if err or not dur:
            broken += 1
            updated.append(p.model_copy(update={"status": BankStatus.DRAFT, "duration_s": None}))
        else:
            updated.append(p.model_copy(update={"duration_s": dur}))
    drafts = {p.id for p in updated if p.status is BankStatus.DRAFT}
    questions = [
        q.model_copy(update={"status": BankStatus.DRAFT}) if q.passage_id in drafts else q
        for q in questions
    ]
    write_skill("listening", questions, updated)
    # recordings of texts that changed or left the bank
    wanted = {p.audio for p in updated if p.audio}
    removed = 0
    for f in (AUDIO_DIR / "ls").rglob("*.ogg"):
        if str(f.relative_to(AUDIO_DIR)) not in wanted:
            f.unlink()
            removed += 1
    total = sum(p.duration_s or 0 for p in updated)
    size = sum(f.stat().st_size for f in AUDIO_DIR.rglob("*.ogg"))
    stats = {
        "recordings": len(updated),
        "broken": broken,
        "removed_stale": removed,
        "hours": round(total / 3600, 2),
        "megabytes": round(size / 1e6, 1),
    }
    log(f"audio: {stats}")
    return stats
