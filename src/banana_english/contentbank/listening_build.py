"""Build the listening pool. Three kinds of recordings (all synthesised later by `audio`):

  * everyday texts from templates (A1-A2): detail and true/false questions;
  * single sentences (Tatoeba, A1-B1): dictation + "which sentence did you hear?" (the
    distractors differ by one sound-level change: tense, number, pronoun or a digit);
  * short Wikipedia paragraphs (B1-C1), other articles than the reading ones: main idea,
    true/false, detail and vocabulary questions.
Every recording has at least two questions.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from itertools import islice

from banana_english.contentbank import sources
from banana_english.contentbank.build import allocate, choice_question, stable_id
from banana_english.contentbank.corpus import tatoeba_sentences, vietnamese_translations
from banana_english.contentbank.lexicon import LEVELS, length_level, level_of_words, max_level
from banana_english.contentbank.nlp import parsed
from banana_english.contentbank.reading_gen import passage_questions, template_records, wiki_passage
from banana_english.contentbank.schema import PassageRecord, QuestionRecord, SourceRef
from banana_english.contentbank.store import write_skill
from banana_english.contentbank.templates import generate
from banana_english.domain.models.bank import BankStatus

TARGET = 26_000
LEVEL_WEIGHTS = {"A1": 20, "A2": 24, "B1": 24, "B2": 18, "C1": 14}
READING_WIKI = 12_000  # the reading build uses the first articles; listening starts after them
_SWAP_PRONOUN = {
    "he": "she",
    "she": "he",
    "his": "her",
    "her": "his",
    "we": "they",
    "they": "we",
    "him": "her",
    "us": "them",
    "them": "us",
}


def audio_path(pid: str, text: str) -> str:
    """Named after the text too: a changed text gets a new recording, never a stale one."""
    digest = hashlib.sha256(text.encode()).hexdigest()[:8]
    return f"ls/{pid.rsplit('.', 1)[-1][:2]}/{pid}.{digest}.ogg"


def _variants(doc, rng: random.Random) -> list[str]:
    """Sentences that differ from the original by one audible change."""
    from lemminflect import getInflection

    out: list[str] = []
    for t in doc:
        new = None
        if t.lower_ in _SWAP_PRONOUN:
            new = _SWAP_PRONOUN[t.lower_]
            if t.text[0].isupper():
                new = new.capitalize()
        elif t.tag_ == "VBD" and t.lemma_ not in ("be", "have"):
            f = getInflection(t.lemma_, "VBZ")
            new = f[0] if f and f[0] != t.text else None
        elif t.tag_ == "NNS":
            new = t.lemma_ if t.lemma_ != t.lower_ else None
        elif (
            t.tag_ == "NN"
            and t.pos_ == "NOUN"
            and t.i > 0
            and doc[t.i - 1].lower_ not in ("a", "an", "one", "each", "every")
        ):
            f = getInflection(t.lemma_, "NNS")
            new = f[0] if f and f[0] != t.text else None
        elif t.like_num and re.fullmatch(r"\d{1,3}", t.text):
            new = str(int(t.text) + rng.choice([1, 2, 3, 5, 10]))
        if new:
            text = doc[: t.i].text_with_ws + new + t.whitespace_ + doc[t.i + 1 :].text_with_ws
            text = text.strip()
            if text != doc.text and text not in out:
                out.append(text)
    rng.shuffle(out)
    return out[:3]


def sentence_clips(limit: int, log) -> tuple[list[PassageRecord], list[QuestionRecord]]:
    vie = vietnamese_translations()
    passages: list[PassageRecord] = []
    questions: list[QuestionRecord] = []

    def pool():  # sentences with a human Vietnamese translation first: they are the best ones
        for s in tatoeba_sentences(min_words=5, max_words=12):
            if s.ref in vie:
                yield s

    for sentence, doc in parsed("tatoeba-listening", islice(pool(), limit), log=log):
        lemmas = [t.lemma_.lower() for t in doc if t.pos_ in ("NOUN", "VERB", "ADJ", "ADV")]
        level = max_level(level_of_words(lemmas), length_level(sum(not t.is_punct for t in doc)))
        if level not in ("A1", "A2", "B1") or any(t.like_num and len(t.text) > 3 for t in doc):
            continue
        if len(sentence.text) < 20:  # a recording shorter than this is too little to listen to
            continue
        rng = random.Random(sentence.ref)
        variants = _variants(doc, rng)
        if len(variants) < 3:
            continue
        pid = stable_id("ls.s", sentence.ref)
        src = SourceRef(
            id="tatoeba-eng", ref=sentence.ref, license=sources.SOURCE_BY_ID["tatoeba-eng"].license
        )
        passages.append(
            PassageRecord(
                id=pid,
                skill="listening",
                level=level,
                topic="daily_life",
                title="Listen to the sentence",
                text=doc.text,
                audio=audio_path(pid, doc.text),
                source=src,
                quality=0.88,
            )
        )
        meaning = vie.get(sentence.ref, "")
        common = dict(
            skill="listening",
            skill_id="listening.comprehension",
            level=level,
            topic="daily_life",
            passage_id=pid,
            source=src,
        )
        questions.append(
            QuestionRecord(
                id=stable_id("ls.dictation", pid),
                point="dictation",
                difficulty="medium",
                qtype="dictation",
                instruction="Listen and type the sentence you hear.",
                prompt="Type the sentence.",
                answer={"text": doc.text},
                explanation=f"You heard: “{doc.text}”",
                explanation_vi=f"Câu bạn nghe: “{doc.text}”"
                + (f" (Nghĩa: {meaning})" if meaning else ""),
                status=BankStatus.VALIDATED,
                quality=0.88,
                **common,
            )
        )
        q = choice_question(
            qid=stable_id("ls.heard", pid),
            point="heard_sentence",
            difficulty="easy",
            qtype="mcq",
            instruction="Listen. Which sentence did you hear?",
            prompt="Which sentence did you hear?",
            right=doc.text,
            wrong=variants,
            explanation=f"You heard: “{doc.text}”",
            explanation_vi=f"Câu bạn nghe: “{doc.text}”"
            + (f" (Nghĩa: {meaning})" if meaning else ""),
            quality=0.86,
            **common,
        )
        if q:
            questions.append(q)
    return passages, questions


def build_listening(
    log: Callable[[str], None] = print,
    templates: int = 1500,
    sentences: int = 7000,
    wiki: int = 3500,
    target: int = TARGET,
) -> dict:
    from banana_english.contentbank.reading_build import wiki_items
    from banana_english.contentbank.vocab_gen import load_words

    passages: list[PassageRecord] = []
    questions: list[QuestionRecord] = []
    # 1) everyday texts
    for i, t in enumerate(generate(templates, seed="listening-templates")):
        p, qs = template_records(t, "listening", i)
        passages.append(p.model_copy(update={"audio": audio_path(p.id, p.text)}))
        questions.extend(qs)
    log(f"  listening: {len(passages)} everyday texts")
    # 2) sentences
    ps, qs = sentence_clips(sentences, log)
    passages += ps
    questions += qs
    log(f"  listening: {len(ps)} sentence recordings")
    # 3) short Wikipedia paragraphs (articles after the ones reading uses)
    words = load_words(log=lambda _: None)
    synonyms: dict = {}
    from banana_english.contentbank.lexicon import learner_word

    by_pos: dict[str, list[str]] = defaultdict(list)
    for w in words:
        if w.level in ("A2", "B1", "B2"):
            by_pos[w.pos].append(w.lemma)
    for w in words:
        syn = sorted(s for s in w.synonyms if learner_word(s, w.pos))
        if syn:
            synonyms[(w.lemma, w.pos)] = (
                syn[0],
                [x for x in by_pos[w.pos] if x not in w.related][:400],
            )
    for source_id in ("simplewiki", "enwiki-0"):
        items = [
            (t, x)
            for t, x in islice(wiki_items(source_id), READING_WIKI, READING_WIKI + wiki)
            if len(x.split()) <= 130
        ]
        entries = []
        for (title, text), doc in parsed(
            f"{source_id}-listening-leads", items, text_of=lambda x: x[1], log=log
        ):
            p = wiki_passage(source_id, title, text, doc, sources.SOURCE_BY_ID[source_id].license)
            p.id = p.id.replace("rd.w", "ls.w", 1)
            p.skill = "listening"
            if p.level in ("A1", "A2"):
                continue
            entries.append((p, doc))
        titles: dict[str, list[str]] = defaultdict(list)
        for p, _ in entries:
            titles[p.topic].append(p.title)
        for p, doc in entries:
            qs = [q for q in passage_questions(p, doc, titles, synonyms) if q]
            if len(qs) < 3:
                continue
            passages.append(
                PassageRecord(
                    id=p.id,
                    skill="listening",
                    level=p.level,
                    topic=p.topic,
                    # not the article title: it is the answer to "what is it mainly about?"
                    title="Listen to the recording",
                    text=p.text,
                    audio=audio_path(p.id, p.text),
                    source=p.source,
                    quality=round(p.quality, 3),
                )
            )
            questions.extend(qs)
        log(f"  listening: {source_id} {len(entries)} paragraphs")
    # balance by level, whole recordings at a time
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
        if len(qs) >= 2 and taken[lvl] + len(qs) <= quota.get(lvl, 0) + 5:
            taken[lvl] += len(qs)
            kept_q.extend(qs)
            kept_p.append(p)
    info = write_skill("listening", kept_q, kept_p)
    stats = {
        "recordings": len(kept_p),
        "questions": info["questions"],
        "by_level": {lvl: taken[lvl] for lvl in LEVELS},
        "by_point": dict(Counter(q.point for q in kept_q)),
        "available": dict(level_avail),
    }
    log(f"listening: {json.dumps(stats)}")
    return stats
