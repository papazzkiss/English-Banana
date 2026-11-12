"""Deterministic fluency metrics from an STT transcript (no LLM).

This measures delivery (speed, fillers, long pauses) — NOT pronunciation. Phoneme-level
pronunciation scoring needs forced alignment / wav2vec2-style models and is out of scope.

Score (0-100, unified rubric scale):
* speech rate: 100 inside 100-160 words/min; linear to 0 at 40 wpm; to 60 at 220 wpm
* minus 5 per filler word per minute of speech (um, uh, er, erm, hmm), max -30
* minus 5 per pause longer than 1.5 s, max -20
* fewer than 5 words -> 0 (not enough speech to judge)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FILLERS = frozenset({"um", "umm", "uh", "uhh", "er", "erm", "hmm", "ah"})
LONG_PAUSE_SECONDS = 1.5
MIN_WORDS = 5


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class FluencyMetrics:
    word_count: int
    speech_seconds: float
    words_per_minute: float
    filler_count: int
    long_pauses: int
    score: float


def _rate_score(wpm: float) -> float:
    if 100 <= wpm <= 160:
        return 100.0
    if wpm < 100:
        return max(0.0, (wpm - 40) / 60 * 100)
    return max(60.0, 100 - (wpm - 160) / 60 * 40)


def fluency_metrics(segments: list[Segment], transcript: str) -> FluencyMetrics:
    words = re.findall(r"[A-Za-z']+", transcript.lower())
    fillers = sum(1 for w in words if w in FILLERS)
    speech = sum(max(0.0, s.end - s.start) for s in segments)
    pauses = sum(
        1
        for prev, cur in zip(segments, segments[1:], strict=False)
        if cur.start - prev.end > LONG_PAUSE_SECONDS
    )
    content_words = len(words) - fillers
    if content_words < MIN_WORDS or speech <= 0:
        return FluencyMetrics(content_words, round(speech, 2), 0.0, fillers, pauses, 0.0)
    minutes = speech / 60
    wpm = content_words / minutes
    score = _rate_score(wpm)
    score -= min(30.0, 5 * fillers / max(minutes, 1 / 6))
    score -= min(20.0, 5 * pauses)
    return FluencyMetrics(
        word_count=content_words,
        speech_seconds=round(speech, 2),
        words_per_minute=round(wpm, 1),
        filler_count=fillers,
        long_pauses=pauses,
        score=round(max(0.0, min(100.0, score)), 1),
    )
