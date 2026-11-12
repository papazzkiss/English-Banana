"""Streaming readers for the source corpora, with the filters every generator relies on."""

from __future__ import annotations

import bz2
import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache

from banana_english.contentbank import sources
from banana_english.contentbank.lexicon import is_clean

_GOOD_SENTENCE = re.compile(r"^[A-Z][A-Za-z0-9 ,.'?!;:\-]*[.?!]$")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class Sentence:
    id: str  # "tatoeba:1277" / "simplewiki:<title>#p1s2"
    text: str
    source: str  # sources.py id
    ref: str


def tatoeba_sentences(min_words: int = 3, max_words: int = 28) -> Iterator[Sentence]:
    """English Tatoeba sentences that are clean, plain ASCII, well punctuated and unique."""
    seen: set[str] = set()
    with bz2.open(sources.path("tatoeba-eng"), "rt", encoding="utf-8") as f:
        for line in f:
            try:
                sid, _lang, text = line.rstrip("\n").split("\t", 2)
            except ValueError:
                continue
            text = _SPACES.sub(" ", text.strip())
            n = text.count(" ") + 1
            if not (min_words <= n <= max_words) or not _GOOD_SENTENCE.match(text):
                continue
            key = text.lower()
            if key in seen or not is_clean(text):
                continue
            seen.add(key)
            yield Sentence(f"tatoeba:{sid}", text, "tatoeba-eng", sid)


@cache
def vietnamese_translations() -> dict[str, str]:
    """Tatoeba English sentence id -> one Vietnamese translation."""
    vie: dict[str, str] = {}
    with bz2.open(sources.path("tatoeba-vie"), "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t", 2)
            if len(parts) == 3:
                vie[parts[0]] = parts[2]
    out: dict[str, str] = {}
    with bz2.open(sources.path("tatoeba-eng-vie"), "rt", encoding="utf-8") as f:
        for line in f:
            eng, _, v = line.rstrip("\n").partition("\t")
            if v in vie and eng not in out:
                out[eng] = vie[v]
    return out


# --- Wikipedia ------------------------------------------------------------------------------

_PAREN_EMPTY = re.compile(r"\s*\((?:[;,\s]*)\)")
# tables, templates, links, and the traces of removed non-Latin text ("the Latin , which")
_BAD_PARAGRAPH = re.compile(
    r"(\|\s|\{\{|\}\}|==|https?://|\bISBN\b|\^|\[\d+\]| [,.;:)]|\(\s*[-,;:)]|\(\s*$)"
)
_SKIP_TITLE = re.compile(r"^(List of|Lists of|Index of|Outline of|Timeline of)|\(disambiguation\)")


@dataclass(frozen=True)
class Article:
    source: str
    title: str
    paragraphs: list[str]


def _clean_paragraph(p: str) -> str:
    p = _PAREN_EMPTY.sub("", p)
    return _SPACES.sub(" ", p).strip()


def wiki_articles(source_id: str, limit: int | None = None) -> Iterator[Article]:
    """Articles with their prose paragraphs (lists, tables, headings and references dropped)."""
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(sources.path(source_id))
    n = 0
    for batch in pf.iter_batches(batch_size=512, columns=["title", "text"]):
        for row in batch.to_pylist():
            title = row["title"]
            if _SKIP_TITLE.search(title):
                continue
            paragraphs = []
            for raw in row["text"].split("\n"):
                p = _clean_paragraph(raw)
                words = p.count(" ") + 1
                if words < 25 or _BAD_PARAGRAPH.search(p) or not p.endswith("."):
                    continue
                if not is_clean(p):
                    continue
                paragraphs.append(p)
            if paragraphs:
                yield Article(source_id, title, paragraphs)
                n += 1
                if limit and n >= limit:
                    return
