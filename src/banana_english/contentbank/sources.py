"""Open-licensed corpora the question bank is generated from.

Downloaded once into var/content_sources/ (not shipped in images). Every file is recorded with
its URL, licence and SHA-256 in sources.lock.json, and the licence travels with every item
generated from it (the item's `source` field).
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from banana_english.config.settings import PROJECT_ROOT

SOURCE_DIR = PROJECT_ROOT / "var" / "content_sources"


@dataclass(frozen=True)
class Source:
    id: str
    url: str
    filename: str
    license: str
    citation: str


TATOEBA = "Tatoeba (https://tatoeba.org), sentences and translations"
WIKIPEDIA = "Wikipedia, via the wikimedia/wikipedia dataset (20231101)"

SOURCES = (
    Source(
        "tatoeba-eng",
        "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2",
        "eng_sentences.tsv.bz2",
        "CC BY 2.0 FR",
        TATOEBA,
    ),
    Source(
        "tatoeba-vie",
        "https://downloads.tatoeba.org/exports/per_language/vie/vie_sentences.tsv.bz2",
        "vie_sentences.tsv.bz2",
        "CC BY 2.0 FR",
        TATOEBA,
    ),
    Source(
        "tatoeba-eng-vie",
        "https://downloads.tatoeba.org/exports/per_language/eng/eng-vie_links.tsv.bz2",
        "eng-vie_links.tsv.bz2",
        "CC BY 2.0 FR",
        TATOEBA,
    ),
    Source(
        "simplewiki",
        "https://huggingface.co/datasets/wikimedia/wikipedia/resolve/main/"
        "20231101.simple/train-00000-of-00001.parquet",
        "simplewiki-20231101.parquet",
        "CC BY-SA 4.0",
        "Simple English " + WIKIPEDIA,
    ),
    Source(
        "enwiki-0",
        "https://huggingface.co/datasets/wikimedia/wikipedia/resolve/main/"
        "20231101.en/train-00000-of-00041.parquet",
        "enwiki-20231101-00000.parquet",
        "CC BY-SA 4.0",
        "English " + WIKIPEDIA,
    ),
)
WIKTIONARY = "Wiktionary, extracted by wiktextract (kaikki.org)"
SOURCES += (
    Source(
        "viwiktionary",
        "https://kaikki.org/viwiktionary/raw-wiktextract-data.jsonl.gz",
        "viwiktionary-wiktextract.jsonl.gz",
        "CC BY-SA 4.0",
        "Vietnamese " + WIKTIONARY,
    ),
    Source(
        "enwiktionary-vi",
        "https://kaikki.org/dictionary/Vietnamese/kaikki.org-dictionary-Vietnamese.jsonl.gz",
        "enwiktionary-vietnamese.jsonl.gz",
        "CC BY-SA 4.0",
        "English " + WIKTIONARY + ", Vietnamese entries",
    ),
)
SOURCE_BY_ID = {s.id: s for s in SOURCES}


def path(source_id: str) -> Path:
    return SOURCE_DIR / SOURCE_BY_ID[source_id].filename


def _sha256(file: Path) -> str:
    h = hashlib.sha256()
    with file.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(log=print) -> dict[str, dict]:
    """Download the missing sources (resumable: a partial file is kept as .part)."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = SOURCE_DIR / "sources.lock.json"
    lock = json.loads(lock_file.read_text()) if lock_file.exists() else {}
    for s in SOURCES:
        target = SOURCE_DIR / s.filename
        if not target.exists():
            part = target.with_suffix(target.suffix + ".part")
            log(f"download {s.id}: {s.url}")
            urllib.request.urlretrieve(s.url, part)
            part.rename(target)
        if s.id not in lock or lock[s.id].get("bytes") != target.stat().st_size:
            lock[s.id] = {
                "url": s.url,
                "file": s.filename,
                "bytes": target.stat().st_size,
                "sha256": _sha256(target),
                "license": s.license,
                "citation": s.citation,
            }
            lock_file.write_text(json.dumps(lock, indent=2))
        log(f"ok {s.id} ({target.stat().st_size / 1e6:.1f} MB, {s.license})")
    return lock
