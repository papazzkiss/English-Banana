"""spaCy parsing with an on-disk cache: sentences are parsed once, in chunks of 20,000, and
saved as DocBin files under var/content_cache/parsed/<name>/. A rebuild (or a resumed one after
an interruption) reads the finished chunks instead of parsing them again."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from functools import cache
from itertools import islice
from pathlib import Path

from banana_english.config.settings import PROJECT_ROOT

CACHE_DIR = PROJECT_ROOT / "var" / "content_cache"
CHUNK = 20_000


@cache
def nlp():
    import spacy

    return spacy.load("en_core_web_sm")


def _chunks(items: Iterable, size: int) -> Iterator[list]:
    it = iter(items)
    while chunk := list(islice(it, size)):
        yield chunk


def parsed(
    name: str,
    items: Iterable,
    text_of: Callable = lambda x: x.text,
    log: Callable[[str], None] = print,
    n_process: int = 3,
) -> Iterator[tuple[object, object]]:
    """Yield (item, Doc) for every item, parsing only the chunks not cached yet.

    `items` must be deterministic (same order every run) so chunk N is always the same items.
    """
    from spacy.tokens import DocBin

    folder = CACHE_DIR / "parsed" / name
    folder.mkdir(parents=True, exist_ok=True)
    model = nlp()
    for i, chunk in enumerate(_chunks(items, CHUNK)):
        path = folder / f"{i:04d}.spacy"
        meta = folder / f"{i:04d}.json"
        texts = [text_of(x) for x in chunk]
        if path.exists() and meta.exists() and json.loads(meta.read_text())["n"] == len(texts):
            docs = list(DocBin().from_disk(path).get_docs(model.vocab))
        else:
            docs = list(model.pipe(texts, batch_size=256, n_process=n_process))
            db = DocBin(
                attrs=[
                    "ORTH",
                    "LEMMA",
                    "POS",
                    "TAG",
                    "DEP",
                    "HEAD",
                    "ENT_IOB",
                    "ENT_TYPE",
                    "MORPH",
                    "SENT_START",
                ]
            )
            for d in docs:
                db.add(d)
            db.to_disk(path)
            meta.write_text(json.dumps({"n": len(texts)}))
            log(f"  parsed {name} chunk {i} ({len(texts):,} texts)")
        yield from zip(chunk, docs, strict=True)


def cache_path(*parts: str) -> Path:
    path = CACHE_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
