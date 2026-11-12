"""Deterministic answer normalisation and comparison (no LLM)."""

from __future__ import annotations

import re
import unicodedata

_QUOTES = str.maketrans({"’": "'", "‘": "'", "`": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_TRAILING_PUNCT = re.compile(r"[\s.!?,;:]+$")
_WHITESPACE = re.compile(r"\s+")


def normalize_answer(text: str) -> str:
    """Case-, whitespace-, quote- and trailing-punctuation-insensitive form of an answer."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    text = _WHITESPACE.sub(" ", text).strip().casefold()
    return _TRAILING_PUNCT.sub("", text)


def matches_any(answer: str, accepted: tuple[str, ...] | list[str]) -> bool:
    normalized = normalize_answer(answer)
    return any(normalized == normalize_answer(a) for a in accepted)


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance (insert/delete/substitute, cost 1 each)."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]
