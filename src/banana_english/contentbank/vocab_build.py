"""Build the vocabulary pool: words -> questions -> balanced selection -> write."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from itertools import islice

from banana_english.contentbank.build import allocate
from banana_english.contentbank.corpus import tatoeba_sentences
from banana_english.contentbank.lexicon import LEVELS, word_level
from banana_english.contentbank.nlp import parsed
from banana_english.contentbank.schema import QuestionRecord
from banana_english.contentbank.store import write_skill
from banana_english.contentbank.vocab_gen import (
    Pools,
    collocation_questions,
    corpus_index,
    load_words,
    matching_questions,
    word_questions,
)

TARGET = 26_000
# share of each question type in the pool (weights; capped by what exists)
TYPE_WEIGHTS = {
    "meaning": 22,
    "definition": 18,
    "vietnamese": 18,
    "synonym": 10,
    "antonym": 5,
    "word_form": 8,
    "context": 12,
    "collocation": 2,
    "matching": 5,
}
LEVEL_WEIGHTS = {"A1": 16, "A2": 20, "B1": 24, "B2": 22, "C1": 18}


def build_vocabulary(log: Callable[[str], None] = print, limit: int | None = None) -> dict:
    words = load_words(log=log)
    targets = {(w.lemma, w.pos): w for w in words}
    sentences = tatoeba_sentences()
    if limit:
        sentences = islice(sentences, limit)
    uses, colloc, colloc_examples = corpus_index(parsed("tatoeba", sentences, log=log), targets)
    pools = Pools(words)
    records: list[QuestionRecord] = []
    for w in words:
        records.extend(q for q in word_questions(w, pools, uses.get((w.lemma, w.pos), [])) if q)
    records.extend(q for q in collocation_questions(colloc, colloc_examples, word_level) if q)
    records.extend(matching_questions(words))
    # dedupe (identical prompts), then balance level x type
    seen: set[str] = set()
    unique = []
    for r in records:
        key = r.id if r.point == "matching" else f"{r.point}|{r.prompt.lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(r)
    by_cell: dict[tuple[str, str], list[QuestionRecord]] = {}
    for r in unique:
        by_cell.setdefault((r.level.value, r.point), []).append(r)
    level_avail = Counter(r.level.value for r in unique)
    level_quota = allocate(dict(level_avail), LEVEL_WEIGHTS, TARGET)
    chosen: list[QuestionRecord] = []
    for level in LEVELS:
        avail = {p: len(by_cell.get((level, p), [])) for p in TYPE_WEIGHTS}
        quota = allocate(avail, TYPE_WEIGHTS, level_quota.get(level, 0))
        for p, n in quota.items():
            chosen.extend(by_cell.get((level, p), [])[:n])
    info = write_skill("vocabulary", chosen)
    stats = {
        "words": len(words),
        "words_with_vietnamese": sum(1 for w in words if w.vi),
        "words_with_one_vietnamese_meaning": sum(1 for w in words if w.vi_sure),
        "candidates": len(records),
        "duplicates": len(records) - len(unique),
        "by_type": dict(Counter(r.point for r in unique)),
        "level_quota": level_quota,
        "written": info["questions"],
    }
    log(f"vocabulary: {json.dumps(stats)}")
    return stats
