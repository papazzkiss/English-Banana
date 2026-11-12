"""Build the grammar pool: parse -> detect -> score -> dedupe -> balance -> write."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from itertools import islice

from banana_english.config.settings import PROJECT_ROOT
from banana_english.contentbank import sources
from banana_english.contentbank.build import (
    Selector,
    allocate,
    choice_question,
    near_duplicate_key,
    stable_id,
    status_for,
    take_balanced,
)
from banana_english.contentbank.corpus import tatoeba_sentences, vietnamese_translations
from banana_english.contentbank.grammar_gen import (
    POINT_LEVEL,
    Candidate,
    candidates,
    difficulty_of,
    item_level,
    topic_for,
)
from banana_english.contentbank.nlp import parsed
from banana_english.contentbank.schema import QuestionRecord, SourceRef
from banana_english.contentbank.store import write_skill

# Share of the pool per grammar point (relative weights; the total is TARGET).
WEIGHTS = {
    "present_simple": 5,
    "present_continuous": 4,
    "past_simple": 6,
    "past_continuous": 4,
    "present_perfect": 5,
    "past_perfect": 3,
    "future_will": 4,
    "modals": 4,
    "conditionals": 3,
    "passive": 5,
    "relative_clauses": 4,
    "articles": 4,
    "prepositions_time": 4,
    "comparatives": 4,
    "superlatives": 3,
    "gerunds_infinitives": 4,
    "there_be": 3,
    "questions_do": 3,
    "quantifiers": 2,
    "reflexive_pronouns": 3,
    "possessives": 3,
    "adjectives_adverbs": 4,
    "contrast_linkers": 3,
    "word_order": 3,
}
TARGET = 26_000


def _points() -> dict[str, str]:
    data = json.loads((PROJECT_ROOT / "content/bank/skills.json").read_text())
    return {k: v["skill_id"] for k, v in data["grammar_points"].items()}


def _quality(c: Candidate, doc, has_translation: bool) -> float:
    words = sum(1 for t in doc if not t.is_punct)
    q = c.base_quality
    if 5 <= words <= 16:
        q += 0.03
    if words > 22:
        q -= 0.06
    names = sum(1 for t in doc if t.pos_ == "PROPN")
    q -= 0.03 * max(0, names - 2)
    if sum(ch.isdigit() for ch in doc.text) > 4:
        q -= 0.04
    if has_translation:
        q += 0.02  # a sentence someone cared to translate is usually a good one
    return max(0.0, min(1.0, q))


def to_record(c: Candidate, doc, sentence, skill_ids: dict[str, str], vie: str | None):
    level = item_level(doc, c.point)
    difficulty = difficulty_of(sum(1 for t in doc if not t.is_punct), c.qtype)
    topic = topic_for(doc)
    quality = _quality(c, doc, vie is not None)
    source = SourceRef(
        id=sentence.source, ref=sentence.ref, license=sources.SOURCE_BY_ID[sentence.source].license
    )
    explanation_vi = c.explanation_vi + (f" (Nghĩa của câu: {vie})" if vie else "")
    qid = stable_id(f"gr.{c.point}", c.qtype, c.prompt, "|".join(c.options or c.accepted))
    common = dict(
        qid=qid,
        skill="grammar",
        skill_id=skill_ids[c.point],
        level=level,
        topic=topic,
        point=c.point,
        difficulty=difficulty,
        qtype=c.qtype,
        prompt=c.prompt,
        instruction=c.instruction,
        explanation=c.explanation,
        explanation_vi=explanation_vi,
        source=source,
        quality=quality,
        tags=c.tags,
    )
    if c.qtype in ("mcq", "error_id"):
        return choice_question(right=c.options[0], wrong=c.options[1:], **common)
    q = {k: v for k, v in common.items() if k != "qid"}
    if c.qtype == "fill_blank":
        return QuestionRecord(
            id=qid,
            answer={"accepted": c.accepted},
            status=status_for(quality),
            **{**q, "quality": round(quality, 3)},
        )
    if c.qtype == "ordering":
        return QuestionRecord(
            id=qid,
            answer={"order": c.pieces},
            display={"pieces": c.options},
            status=status_for(quality),
            **{**q, "quality": round(quality, 3)},
        )
    return None


def build_grammar(log: Callable[[str], None] = print, limit: int | None = None) -> dict:
    skill_ids = _points()
    vie = vietnamese_translations()
    selector = Selector(cap_per_bucket=600)
    rejected = Counter()
    sentences = tatoeba_sentences()
    if limit:
        sentences = islice(sentences, limit)
    for n, (sentence, doc) in enumerate(parsed("tatoeba", sentences, log=log), start=1):
        translation = vie.get(sentence.ref)
        for c in candidates(doc):
            if c.point not in skill_ids:
                continue
            try:
                record = to_record(c, doc, sentence, skill_ids, translation)
            except ValueError as exc:  # failed a record check
                rejected[str(exc).split("\n")[1][:60] if "\n" in str(exc) else "invalid"] += 1
                continue
            if record is None:
                rejected["options clash"] += 1
                continue
            key = f"{c.point}|{c.qtype}|{near_duplicate_key(doc.text)}"
            selector.offer((c.point, record.level.value, c.qtype), key, record)
        if n % 200_000 == 0:
            log(f"  {n:,} sentences, {selector.offered:,} candidates")
    buckets = selector.buckets()
    served = {b: [r for r in rs if r.status.value == "validated"] for b, rs in buckets.items()}
    available = Counter()
    for (point, _level, _qtype), rs in served.items():
        available[point] += len(rs)
    quotas = allocate(available, WEIGHTS, TARGET)
    chosen = take_balanced(served, quotas, point_levels=POINT_LEVEL)
    info = write_skill("grammar", chosen)
    stats = {
        "sentences": n,
        "candidates": selector.offered,
        "near_duplicates": selector.duplicates,
        "rejected": dict(rejected),
        "available": dict(available),
        "quotas": quotas,
        "written": info["questions"],
    }
    log(f"grammar: {json.dumps(stats)}")
    return stats
