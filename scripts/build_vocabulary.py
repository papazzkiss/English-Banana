"""Build content/vocabulary/vocabulary.json from real, legally usable sources.

Sources
-------
* CEFR level, headword, part of speech:
  CEFR-J Vocabulary Profile 1.5 (Tono Laboratory, TUFS), redistributed by
  Open Language Profiles. Free for research and commercial use with citation.
* Definition and example sentence:
  Open English WordNet 2024 (CC BY 4.0).

The join (CEFR-J headword -> WordNet sense) is automatic, so every item is marked
``review_status: "auto_mapped"``. See docs/decisions/phase-0-scope.md.

Usage::

    uv run --group content python scripts/build_vocabulary.py

The WordNet download (~13 MB) is cached in $WN_DATA_DIR (default ~/.wn_data).
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter
from pathlib import Path

import wn

ROOT = Path(__file__).resolve().parents[1]
CEFRJ_CSV = ROOT / "content/vocabulary/sources/cefrj-vocabulary-profile-1.5.csv"
OUTPUT = ROOT / "content/vocabulary/vocabulary.json"
WORDNET_ID = "oewn:2024"

# CEFR-J part-of-speech labels that exist in WordNet. Function words (determiners,
# prepositions, pronouns, ...) have no WordNet entry and belong to grammar anyway.
POS_TO_WORDNET = {"noun": "n", "verb": "v", "adjective": "a", "adverb": "r"}
MAX_SENSE_RANK = 3

SOURCES = [
    {
        "id": "cefrj-1.5",
        "provides": ["word", "part_of_speech", "cefr_level"],
        "citation": (
            "The CEFR-J Wordlist Version 1.5. Compiled by Yukio Tono, Tokyo University of "
            "Foreign Studies. Retrieved from http://www.cefr-j.org/download.html via "
            "https://github.com/openlanguageprofiles/olp-en-cefrj"
        ),
        "license": (
            "Free for research and commercial purposes provided the dataset is cited. "
            "Copyright Tono Laboratory, TUFS."
        ),
    },
    {
        "id": WORDNET_ID,
        "provides": ["definition", "example"],
        "citation": (
            "McCrae et al. Open English WordNet 2024. https://github.com/globalwordnet/english-wordnet"
        ),
        "license": "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0)",
    },
]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def contains_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text, re.IGNORECASE) is not None


def choose_sense(en: wn.Wordnet, variants: list[str], pos: str):
    """Pick the most frequent sense that yields a usable learner item.

    Preference order within the top MAX_SENSE_RANK senses:
      1. definition does not contain the headword AND an example contains it
      2. definition does not contain the headword (no usable example)
      3. the most frequent sense, as-is
    Returns (sense, rank, example) or None.
    """
    headword = variants[0]
    words = [w for w in en.words(headword, pos=pos) if w.lemma() == headword]
    if not words:
        return None
    senses = words[0].senses()[:MAX_SENSE_RANK]
    fallback = None
    for rank, sense in enumerate(senses, start=1):
        synset = sense.synset()
        definition = synset.definition() or ""
        if any(contains_word(definition, v) for v in variants):
            continue
        example = next(
            (ex for ex in synset.examples() if any(contains_word(ex, v) for v in variants)),
            None,
        )
        if example:
            return sense, rank, example
        fallback = fallback or (sense, rank, None)
    return fallback or (senses[0], 1, None)


def main() -> None:
    wn.config.data_directory = os.environ.get("WN_DATA_DIR", str(Path.home() / ".wn_data"))
    try:
        en = wn.Wordnet(WORDNET_ID)
    except wn.Error:
        wn.download(WORDNET_ID)
        en = wn.Wordnet(WORDNET_ID)

    with CEFRJ_CSV.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    items: list[dict] = []
    seen: set[str] = set()
    skipped = Counter()
    for row in rows:
        pos_label = row["pos"].strip()
        wn_pos = POS_TO_WORDNET.get(pos_label)
        if wn_pos is None:
            skipped["function_word_pos"] += 1
            continue
        variants = [v.strip() for v in row["headword"].split("/") if v.strip()]
        item_id = f"{slug(variants[0])}.{pos_label}"
        if item_id in seen:
            skipped["duplicate"] += 1
            continue
        choice = choose_sense(en, variants, wn_pos)
        if choice is None:
            skipped["not_in_wordnet"] += 1
            continue
        sense, rank, example = choice
        seen.add(item_id)
        items.append(
            {
                "id": item_id,
                "word": variants[0],
                "variants": variants[1:],
                "part_of_speech": pos_label,
                "cefr_level": row["CEFR"].strip(),
                "definition": sense.synset().definition(),
                "example": example,
                "provenance": {
                    "level_source": "cefrj-1.5",
                    "sense_source": WORDNET_ID,
                    "sense_id": sense.id,
                    "sense_rank": rank,
                },
                "review_status": "auto_mapped",
            }
        )

    items.sort(key=lambda i: (i["cefr_level"], i["id"]))
    stats = {
        "source_rows": len(rows),
        "items": len(items),
        "items_with_example": sum(1 for i in items if i["example"]),
        "by_level": dict(sorted(Counter(i["cefr_level"] for i in items).items())),
        "by_part_of_speech": dict(sorted(Counter(i["part_of_speech"] for i in items).items())),
        "skipped": dict(sorted(skipped.items())),
    }
    OUTPUT.write_text(
        json.dumps(
            {"schema_version": 1, "sources": SOURCES, "stats": stats, "items": items},
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
