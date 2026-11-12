"""Reading passages and their question pools.

Passages: Simple English Wikipedia (A2-B2) and English Wikipedia (B2-C1) lead paragraphs, plus
everyday A1-A2 texts from templates. Per passage (about five questions, never one):
  * title / main idea: the article's own title against titles of other articles on the topic;
  * true / false: a sentence of the text (true), or the same sentence with one fact changed
    (a number, a name, a negated verb) (false);
  * detail: complete a sentence of the text (the missing number, date or name);
  * vocabulary in context: a synonym of a word of the text (main sense of both words).
Also shared with listening (the questions do not depend on reading vs hearing the text).
"""

from __future__ import annotations

import random
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass

from banana_english.contentbank.build import choice_question, stable_id
from banana_english.contentbank.lexicon import (
    AMBIGUOUS_TOPIC_WORDS,
    LEVELS,
    RANK,
    topic_of,
    word_level,
)
from banana_english.contentbank.schema import PassageRecord, QuestionRecord, SourceRef
from banana_english.contentbank.templates import TemplateText
from banana_english.domain.models.bank import BankStatus

_APPROX = re.compile(
    r"\b(more than|over|about|around|nearly|almost|at least|up to|less than|"
    r"under|some|approximately|roughly|than|above|below|at most)$"
)
# sentences that only make sense after the one before (not usable as statements)
_PRONOUN_START = re.compile(
    r"^(It|They|He|She|This|These|That|Those|Its|Their|His|Her|Others|Some|Many|Most|Both|"
    r"Each|One|Another|Such|There|However|Also|Then|So|But|And|In addition|Therefore)\b"
)


@dataclass
class Passage:
    id: str
    skill: str
    level: str
    topic: str
    title: str
    text: str
    source: SourceRef
    quality: float


def passage_level(doc, source_id: str) -> str:
    sents = list(doc.sents)
    words = [t for t in doc if t.is_alpha]
    avg = len(words) / max(1, len(sents))
    content = [
        t.lemma_.lower() for t in doc if t.pos_ in ("NOUN", "VERB", "ADJ", "ADV") and t.is_alpha
    ]
    ranks = [RANK[word_level(w)] for w in content]
    hard = sum(r >= 3 for r in ranks) / max(1, len(ranks))  # B2 and above
    if source_id == "simplewiki":
        if avg <= 13 and hard <= 0.10:
            return "A2"
        if avg <= 17 and hard <= 0.18:
            return "B1"
        return "B2"
    return "B2" if avg <= 22 and hard <= 0.22 else "C1"


def passage_quality(doc) -> float:
    sents = list(doc.sents)
    q = 0.8
    if len(sents) < 4:
        q -= 0.1
    if sum(1 for t in doc if t.like_num) > 12:
        q -= 0.05
    if any(len(s) > 45 for s in sents):
        q -= 0.05
    return max(0.0, min(1.0, q))


# --- question builders over a parsed passage ----------------------------------------------------


def _statement_sentences(doc) -> list:
    out = []
    for s in doc.sents:
        text = s.text.strip()
        n = sum(1 for t in s if t.is_alpha)
        if (
            6 <= n <= 28
            and text.endswith(".")
            and not _PRONOUN_START.match(text)
            and "(" not in text
        ):
            out.append(s)
    return out


def _negate(sent) -> str | None:
    """'X is Y' -> 'X is not Y'; 'X lives...' -> 'X does not live...' (main verb only)."""
    root = sent.root
    if any(c.dep_ == "neg" for c in root.children):
        return None
    aux = [c for c in root.children if c.dep_ in ("aux", "auxpass")]
    text = sent.text
    offset = sent.start_char
    target = aux[0] if aux else (root if root.lemma_ == "be" else None)
    if target is not None and target.lower_ in (
        "is",
        "are",
        "was",
        "were",
        "can",
        "will",
        "has",
        "have",
        "had",
        "could",
        "would",
    ):
        i = target.idx - offset + len(target.text)
        return text[:i] + " not" + text[i:]
    if not aux and root.tag_ in ("VBZ", "VBD", "VBP") and root.lemma_ != "be":
        do = {"VBZ": "does", "VBD": "did", "VBP": "do"}[root.tag_]
        i = root.idx - offset
        return text[:i] + f"{do} not {root.lemma_}" + text[i + len(root.text) :]
    return None


def _swap_number(sent, rng: random.Random, taken: set[str]) -> tuple[str, str, str] | None:
    """Change one number/year in the sentence; returns (new sentence, old, new)."""
    for t in sent:
        before = sent.doc[max(0, t.i - 2) : t.i].text.lower()
        if _APPROX.search(before):
            continue  # "more than 20" -> "more than 10" would still be true
        if (
            t.like_num
            and re.fullmatch(r"\d{1,4}", t.text)
            and t.ent_type_ in ("DATE", "CARDINAL", "QUANTITY", "")
        ):
            n = int(t.text)
            if 1000 <= n <= 2030:
                cands = [n + d for d in (-20, -10, -5, 5, 10, 15, 30) if 1000 <= n + d <= 2025]
            elif n >= 3:
                cands = [n * 2, n + max(1, n // 2), max(1, n - max(1, n // 2)), n + 7]
            else:
                continue
            cands = [str(c) for c in cands if str(c) not in taken and c != n]
            if not cands:
                continue
            new = rng.choice(cands)
            i = t.idx - sent.start_char
            text = sent.text
            return text[:i] + new + text[i + len(t.text) :], t.text, new
    return None


_NAME_FILLERS = {"the", "of", "and", "a", "an", "in", "on", "for", "de", "la", "le"}


def _same_name(a: str, b: str) -> bool:
    """ "Brunei" / "Brunei Darussalam", "Robot Arena" / "Robot Arena 3": may name the same
    thing, so one is never a distractor for the other."""
    words = lambda x: set(re.findall(r"\w+", x.lower())) - _NAME_FILLERS  # noqa: E731
    return a == b or bool(words(a) & words(b))


def _swap_entity(sent, others: list[tuple[str, str]], rng: random.Random):
    for ent in sent.ents:
        # people and organisations only: another place can still be true (Paris / France)
        if ent.label_ not in ("PERSON", "ORG"):
            continue
        choices = [
            text
            for text, label in others
            if label == ent.label_ and text not in sent.text and not _same_name(text, ent.text)
        ]
        if not choices:
            continue
        new = rng.choice(sorted(set(choices)))
        i = ent.start_char - sent.start_char
        text = sent.text
        return text[:i] + new + text[i + len(ent.text) :], ent.text, new
    return None


def passage_questions(
    p: Passage,
    doc,
    titles_by_topic: dict[str, list[str]],
    synonyms: dict[str, tuple[str, list[str]]],
) -> Iterator[QuestionRecord]:
    rng = random.Random(p.id)
    skill = p.skill
    skill_id = "reading.comprehension" if skill == "reading" else "listening.comprehension"
    prefix = "rd" if skill == "reading" else "ls"
    verb = "text" if skill == "reading" else "recording"
    base = dict(
        skill=skill,
        skill_id=skill_id,
        level=p.level,
        topic=p.topic,
        passage_id=p.id,
        source=p.source,
    )

    def q(point: str, suffix: str, difficulty: str, quality: float, **kw):
        return choice_question(
            qid=stable_id(f"{prefix}.{point}", p.id, suffix),
            point=point,
            difficulty=difficulty,
            quality=quality,
            **base,
            **kw,
        )

    # 1) title / main idea
    others = [
        t
        for t in titles_by_topic.get(p.topic, [])
        if t != p.title and t.lower() not in p.text.lower()
    ]
    if len(others) >= 3:
        wrong = rng.sample(others, 3)
        yield q(
            "main_idea",
            "title",
            "easy",
            min(0.9, p.quality + 0.05),
            qtype="mcq",
            prompt=f"What is the {verb} mainly about?",
            instruction="Choose the best answer.",
            right=p.title,
            wrong=wrong,
            explanation=f"The whole {verb} is about {p.title}.",
            explanation_vi=f"Toàn bộ bài nói về {p.title}.",
        )
    sents = _statement_sentences(doc)
    if not sents:
        return
    ents = [(e.text, e.label_) for e in doc.ents]
    numbers = {t.text for t in doc if t.like_num}
    rng.shuffle(sents)
    # 2) true statement (a sentence of the text) and false ones (one fact changed)
    true_s = sents[0]
    yield q(
        "true_false",
        "true",
        "easy",
        p.quality,
        qtype="true_false",
        prompt=true_s.text.strip(),
        instruction=f"According to the {verb}, is this true or false?",
        right="True",
        wrong=["False"],
        explanation=f"True. The {verb} says: “{true_s.text.strip()}”",
        explanation_vi=f"Đúng. Bài có câu: “{true_s.text.strip()}”",
    )
    made = 0
    for s in sents[1:]:
        if made >= 1:  # one false statement per passage (with the true one: two T/F)
            break
        change = _swap_number(s, rng, numbers) or _swap_entity(s, ents, rng)
        if change:
            new, old, new_part = change
            why = f"'{new_part}' is wrong: the {verb} says '{old}'."
            why_vi = f"Sai: bài nói là '{old}', không phải '{new_part}'."
        else:
            negated = _negate(s)
            if not negated:
                continue
            new = negated
            why = f"The {verb} says the opposite: “{s.text.strip()}”"
            why_vi = f"Bài nói điều ngược lại: “{s.text.strip()}”"
        made += 1
        yield q(
            "true_false",
            f"false{made}",
            "medium",
            p.quality - 0.02,
            qtype="true_false",
            prompt=new.strip(),
            instruction=f"According to the {verb}, is this true or false?",
            right="False",
            wrong=["True"],
            explanation=f"False. {why}",
            explanation_vi=why_vi,
        )
    # 3) detail: the missing number or name
    for s in sents[1:]:
        target = next((t for t in s if t.like_num and re.fullmatch(r"\d{1,4}", t.text)), None)
        if target is not None:
            n = int(target.text)
            pool = sorted(
                {
                    x
                    for x in numbers
                    if re.fullmatch(r"\d{1,4}", x)
                    and x != target.text
                    and abs(len(x) - len(target.text)) <= 1
                }
            )
            wrong = rng.sample(pool, min(3, len(pool)))
            while len(wrong) < 3:
                cand = str(n + rng.choice([-7, -3, -2, 2, 3, 5, 9, 11]) * (10 if n > 1000 else 1))
                if cand not in wrong and cand != target.text and int(cand) > 0:
                    wrong.append(cand)
            gap = (
                s.text[: target.idx - s.start_char]
                + "___"
                + s.text[target.idx - s.start_char + len(target.text) :]
            )
            yield q(
                "detail",
                "number",
                "medium",
                p.quality,
                qtype="mcq",
                prompt=gap.strip(),
                instruction=f"Complete the sentence with information from the {verb}.",
                right=target.text,
                wrong=wrong,
                explanation=f"The {verb} says: “{s.text.strip()}”",
                explanation_vi=f"Bài viết: “{s.text.strip()}”",
            )
            break
    else:
        for s in sents[1:]:
            ent = next((e for e in s.ents if e.label_ in ("PERSON", "GPE", "ORG", "LOC")), None)
            if ent is None:
                continue
            pool = sorted(
                {
                    t
                    for t, lab in ents
                    if lab == ent.label_ and t not in s.text and not _same_name(t, ent.text)
                }
            )
            if len(pool) < 3:
                continue
            gap = s.text.replace(ent.text, "___", 1)
            yield q(
                "detail",
                "name",
                "medium",
                p.quality - 0.02,
                qtype="mcq",
                prompt=gap.strip(),
                instruction=f"Complete the sentence with information from the {verb}.",
                right=ent.text,
                wrong=rng.sample(pool, 3),
                explanation=f"The {verb} says: “{s.text.strip()}”",
                explanation_vi=f"Bài viết: “{s.text.strip()}”",
            )
            break
    # 4) vocabulary in context: the same part of speech as the synonym's entry
    pos_name = {"ADJ": "adjective", "VERB": "verb", "NOUN": "noun"}
    for t in doc:
        key = t.lemma_.lower()
        entry = (key, pos_name.get(t.pos_, ""))
        if entry in synonyms and t.lower_ == key and RANK[word_level(key)] >= 2:
            syn, distractors = synonyms[entry]
            if len(distractors) < 3 or syn.lower() in p.text.lower():
                continue
            yield q(
                "vocabulary_in_context",
                key,
                "hard",
                p.quality - 0.06,
                qtype="mcq",
                prompt=f"In the {verb}, the word “{t.text}” is closest in meaning to:",
                instruction="Choose the best answer.",
                right=syn,
                wrong=rng.sample(distractors, 3),
                explanation=f"'{t.text}' here means the same as '{syn}'.",
                explanation_vi=f"Trong bài, '{t.text}' có nghĩa giống '{syn}'.",
            )
            break


def template_records(
    t: TemplateText, skill: str, idx: int
) -> tuple[PassageRecord, list[QuestionRecord]]:
    prefix = "rd" if skill == "reading" else "ls"
    pid = stable_id(f"{prefix}.t.{t.family}", t.text)
    src = SourceRef(id=f"template:{t.family}", ref=str(idx), license="Banana English (original)")
    passage = PassageRecord(
        id=pid,
        skill=skill,
        level=t.level,
        topic=t.topic,
        title=t.title,
        text=t.text,
        source=src,
        quality=0.9,
    )
    skill_id = "reading.comprehension" if skill == "reading" else "listening.comprehension"
    records = []
    for i, tq in enumerate(t.questions):
        tf = tq.kind == "true_false"
        rec = choice_question(
            qid=stable_id(f"{prefix}.{'true_false' if tf else 'detail'}", pid, str(i)),
            skill=skill,
            skill_id=skill_id,
            level=t.level,
            topic=t.topic,
            point="true_false" if tf else "detail",
            difficulty="easy" if tf else "medium",
            qtype="true_false" if tf else "mcq",
            prompt=tq.prompt,
            instruction=(
                f"According to the {'text' if skill == 'reading' else 'recording'}, "
                "is this true or false?"
            )
            if tf
            else "Choose the right answer.",
            right=tq.right,
            wrong=tq.wrong,
            explanation=tq.explanation,
            explanation_vi=tq.explanation_vi,
            source=src,
            quality=0.9,
            passage_id=pid,
        )
        if rec:
            records.append(rec)
    return passage, records


def level_counts(records) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for r in records:
        out[r.level.value] += 1
    return {lvl: out[lvl] for lvl in LEVELS}


def wiki_passage(source_id: str, title: str, text: str, doc, license_: str) -> Passage:
    level = passage_level(doc, source_id)
    # the first sentence says what the article is ("... is a 1998 film"): it counts three times
    first = next(iter(doc.sents), None)
    lead = [t.lemma_.lower() for t in first if t.pos_ == "NOUN"] if first is not None else []
    topic = topic_of(
        [t.lemma_.lower() for t in doc if t.pos_ == "NOUN"] + title.lower().split() + lead * 2,
        default="society",
        min_hits=3,
        margin=1.5,
        skip=AMBIGUOUS_TOPIC_WORDS,
    )
    prefix = "rd.w"
    return Passage(
        id=stable_id(prefix, source_id, title),
        skill="reading",
        level=level,
        topic=topic,
        title=title,
        text=text,
        source=SourceRef(id=source_id, ref=title, license=license_),
        quality=passage_quality(doc),
    )


__all__ = ["BankStatus", "Passage", "passage_questions", "template_records", "wiki_passage"]
