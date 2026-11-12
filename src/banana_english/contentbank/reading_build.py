"""Build the reading pool: passages (Wikipedia + everyday templates) with ~5 questions each."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from itertools import islice

from banana_english.contentbank import sources
from banana_english.contentbank.build import allocate
from banana_english.contentbank.corpus import wiki_articles
from banana_english.contentbank.lexicon import LEVELS, learner_word
from banana_english.contentbank.nlp import parsed
from banana_english.contentbank.reading_gen import (
    passage_questions,
    template_records,
    wiki_passage,
)
from banana_english.contentbank.schema import PassageRecord, QuestionRecord
from banana_english.contentbank.store import write_skill
from banana_english.contentbank.templates import generate

TARGET = 26_000
LEVEL_WEIGHTS = {"A1": 14, "A2": 22, "B1": 24, "B2": 22, "C1": 18}
STUB = re.compile(
    r"\bis an? (commune|municipality|town|village|city|comune|species|genus|"
    r"district|county|census|parish|hamlet|borough|suburb|river in|lake in|"
    r"asteroid|footballer|politician|album|single|song by)\b",
    re.I,
)
PER_TOPIC = {"simplewiki": 400, "enwiki-0": 260}


def lead_text(paragraphs: list[str]) -> str | None:
    text = paragraphs[0]
    if len(text.split()) < 80 and len(paragraphs) > 1:
        text = f"{text} {paragraphs[1]}"
    n = len(text.split())
    if not 70 <= n <= 230 or STUB.search(text.split(".")[0]):
        return None
    return text


def wiki_items(source_id: str) -> Iterator[tuple[str, str]]:
    """(title, lead text) of articles with a usable lead paragraph."""
    for a in wiki_articles(source_id):
        text = lead_text(a.paragraphs)
        if text and len(a.title) <= 60:
            yield (a.title, text)


def build_reading(
    log: Callable[[str], None] = print,
    wiki_limit: int = 12_000,
    templates: int = 1600,
    skill: str = "reading",
    target: int = TARGET,
) -> dict:
    """The listening build reuses this with skill="listening" (texts read aloud later)."""
    from banana_english.contentbank.vocab_gen import load_words

    words = load_words(log=log)
    by_pos: dict[str, list[str]] = defaultdict(list)
    for w in words:
        if w.level in ("A2", "B1", "B2") and re.fullmatch(r"[a-z]+", w.lemma):
            by_pos[w.pos].append(w.lemma)
    synonyms: dict[str, tuple[str, list[str]]] = {}
    for w in words:
        syn = sorted(s for s in w.synonyms if learner_word(s, w.pos))
        if syn:
            pool = [x for x in by_pos[w.pos] if x not in w.related and x != syn[0]][:400]
            synonyms[(w.lemma, w.pos)] = (syn[0], pool)

    passages: list[PassageRecord] = []
    questions: list[QuestionRecord] = []
    # everyday texts (A1-A2)
    for i, t in enumerate(generate(templates, seed=f"{skill}-templates")):
        p, qs = template_records(t, skill, i)
        passages.append(p)
        questions.extend(qs)
    log(f"  {skill}: {len(passages)} template texts, {len(questions)} questions")

    # Wikipedia: first gather passages per topic (for title distractors), then questions
    for source_id in ("simplewiki", "enwiki-0"):
        license_ = sources.SOURCE_BY_ID[source_id].license
        items = list(islice(wiki_items(source_id), wiki_limit))
        per_topic: Counter = Counter()
        entries = []
        for (title, text), doc in parsed(
            f"{source_id}-{skill}-leads", items, text_of=lambda x: x[1], log=log
        ):
            p = wiki_passage(source_id, title, text, doc, license_)
            if skill == "listening":
                p.id = p.id.replace("rd.w", "ls.w", 1)
                p.skill = "listening"
            if per_topic[p.topic] >= PER_TOPIC[source_id]:
                continue
            per_topic[p.topic] += 1
            entries.append((p, doc))
        titles: dict[str, list[str]] = defaultdict(list)
        for p, _ in entries:
            titles[p.topic].append(p.title)
        n_before = len(questions)
        for p, doc in entries:
            qs = [q for q in passage_questions(p, doc, titles, synonyms) if q]
            if len(qs) < 3:
                continue  # a passage needs its own small pool of questions
            passages.append(
                PassageRecord(
                    id=p.id,
                    skill=p.skill,
                    level=p.level,
                    topic=p.topic,
                    # not the article title: it is the answer to "what is it mainly about?"
                    title="Read the text",
                    text=p.text,
                    source=p.source,
                    quality=round(p.quality, 3),
                )
            )
            questions.extend(qs)
        log(
            f"  {skill}: {source_id} {len(entries)} passages -> {len(questions) - n_before} "
            f"questions"
        )

    # balance by level, keeping whole passages
    by_passage: dict[str, list[QuestionRecord]] = defaultdict(list)
    for q in questions:
        by_passage[q.passage_id].append(q)
    level_avail = Counter(q.level.value for q in questions)
    quota = allocate(dict(level_avail), LEVEL_WEIGHTS, target)
    kept_q: list[QuestionRecord] = []
    kept_p: list[PassageRecord] = []
    taken: Counter = Counter()
    for p in sorted(passages, key=lambda p: (-p.quality, p.id)):
        qs = by_passage.get(p.id, [])
        lvl = p.level.value
        if qs and taken[lvl] + len(qs) <= quota.get(lvl, 0) + 5:
            taken[lvl] += len(qs)
            kept_q.extend(qs)
            kept_p.append(p)
    info = write_skill(skill, kept_q, kept_p)
    stats = {
        "passages": len(kept_p),
        "questions": info["questions"],
        "by_level": {lvl: taken[lvl] for lvl in LEVELS},
        "by_point": dict(Counter(q.point for q in kept_q)),
        "available": dict(level_avail),
    }
    log(f"{skill}: {json.dumps(stats)}")
    return stats
