"""Vocabulary questions: the existing CEFR-J x Open English WordNet word list (A1-B2), plus
C1 words from WordNet by frequency, Vietnamese meanings from the Vietnamese Wiktionary, and
real sentences (Tatoeba) for context, word-form and collocation questions.

Distractors are always checked: same part of speech and similar level, never a synonym, an
antonym or a member of the target's word family, and a different definition.
"""

from __future__ import annotations

import gzip
import json
import os
import random
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import cache

from wordfreq import zipf_frequency

from banana_english.config.settings import PROJECT_ROOT
from banana_english.contentbank import sources
from banana_english.contentbank.build import choice_question, stable_id
from banana_english.contentbank.lexicon import (
    RANK,
    cefrj,
    is_clean,
    learner_word,
    topic_of,
    zipf,
)
from banana_english.contentbank.schema import OptionRecord, QuestionRecord, SourceRef
from banana_english.domain.models.bank import BankStatus

WN_POS = {"noun": "n", "verb": "v", "adjective": "a", "adverb": "r"}
POS_VI = {"noun": "danh từ", "verb": "động từ", "adjective": "tính từ", "adverb": "trạng từ"}
LEVELS5 = ("A1", "A2", "B1", "B2", "C1")


@dataclass
class Word:
    id: str
    lemma: str
    pos: str
    level: str
    definition: str
    example: str | None
    vi: str | None = None  # shown in explanations: the meaning, or two if it is ambiguous
    vi_sure: bool = False  # one clear meaning: a Vietnamese-meaning question can ask for it
    vi_all: frozenset[str] = frozenset()  # every Vietnamese meaning (never a distractor)
    synonyms: set[str] = field(default_factory=set)
    antonyms: set[str] = field(default_factory=set)
    family: dict[str, str] = field(default_factory=dict)  # pos -> lemma
    related: set[str] = field(default_factory=set)  # every lemma that must not be a distractor
    lexfile: str = ""
    senses: int = 0  # how many WordNet senses the word has (for its part of speech)


@cache
def wordnet():
    import wn

    wn.config.data_directory = os.environ.get("WN_DATA_DIR", os.path.expanduser("~/.wn_data"))
    return wn.Wordnet("oewn:2024")


# --- Vietnamese meanings ---------------------------------------------------------------------

_VI_POS = {
    "noun": "noun",
    "verb": "verb",
    "adj": "adjective",
    "adv": "adverb",
    "adjective": "adjective",
    "adverb": "adverb",
}
_VI_CLEAN = re.compile(r"\s*[\(\[][^)\]]*[\)\]]\s*")


# Wiktionary notes, not meanings: "xem permanent" (see ...), "như dad", "dạng quá khứ của ..."
_VI_META = re.compile(
    r"^(xem (?!xét)|như |dạng |cách viết|cách nói khác|số nhiều|quá khứ|phân từ|lỗi chính tả|"
    r"viết tắt|từ viết tắt|nghĩa$)"
)


def _clean_vi(gloss: str) -> str | None:
    text = _VI_CLEAN.sub(" ", gloss).strip().rstrip(".").strip()
    text = text.split(";")[0].split(",")[0].strip()
    if (
        not text
        or len(text) > 40
        or any(c in text for c in "=:/")
        or not re.search(r"[a-zà-ỹđ]", text, re.I)
        or _VI_META.match(text.lower())
    ):
        return None
    return text[0].lower() + text[1:]


@cache
def english_words_of_vietnamese() -> dict[str, set[str]]:
    """English word -> Vietnamese words whose English Wiktionary entry glosses them with it
    ("bay" -> {"vịnh"}): the reverse direction, to tell the everyday sense from a rare one."""
    out: dict[str, set[str]] = defaultdict(set)
    with gzip.open(sources.path("enwiktionary-vi"), "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("pos") == "character" or not d.get("word"):
                continue
            vi = d["word"].lower()
            for sense in d.get("senses", []):
                for gloss in sense.get("glosses", []):
                    for part in re.split(r"[;,]", re.sub(r"\([^)]*\)", "", gloss)):
                        en = re.sub(r"^(to|a|an|the)\s+", "", part.strip().lower())
                        if en and len(en.split()) <= 3:
                            out[en].add(vi)
    return out


@dataclass(frozen=True)
class ViMeaning:
    text: str
    sure: bool
    all: frozenset[str]


@cache
def vietnamese_meanings() -> dict[tuple[str, str], ViMeaning]:
    """(english lemma, part of speech) -> its Vietnamese meaning (Vietnamese Wiktionary).

    A word often has several entries ("bay": ngựa hồng, vịnh). The meaning that the English
    Wiktionary confirms from the Vietnamese side is the sure one (the most frequent if
    several), and a word with a single meaning is sure too. An ambiguous, unconfirmed word
    shows its first two meanings in explanations but gets no Vietnamese-meaning question:
    it could have two right answers."""
    candidates: dict[tuple[str, str], list[str]] = defaultdict(list)
    with gzip.open(sources.path("viwiktionary"), "rt", encoding="utf-8") as f:
        for line in f:
            if '"lang_code": "en"' not in line:
                continue
            d = json.loads(line)
            pos = _VI_POS.get(d.get("pos", ""))
            word = d.get("word", "").lower()
            if not pos or not word:
                continue
            for sense in d.get("senses", []):
                vi = next((v for v in map(_clean_vi, sense.get("glosses", [])) if v), None)
                if vi and vi not in candidates[(word, pos)]:
                    candidates[(word, pos)].append(vi)
    reverse = english_words_of_vietnamese()
    out: dict[tuple[str, str], ViMeaning] = {}
    for (word, pos), vis in candidates.items():
        back = reverse.get(word, set())
        # "nhà ngân hàng" is confirmed by "ngân hàng" (a word of two syllables or more inside it)
        confirmed = [v for v in vis if v.lower() in back] + [
            r for v in vis for r in back if " " in r and f" {r} " in f" {v.lower()} " and r != v
        ]
        every = frozenset(v.lower() for v in vis + confirmed)
        if confirmed:  # the most frequent Vietnamese word: "ngân hàng" before "bờ" for "bank"
            best = max(confirmed, key=lambda v: zipf_frequency(v, "vi"))
            out[(word, pos)] = ViMeaning(best, True, every)
        else:
            out[(word, pos)] = ViMeaning("; ".join(vis[:2]), len(vis) == 1, every)
    return out


# --- the word list ---------------------------------------------------------------------------


def _relations(w: Word) -> None:
    en = wordnet()
    words = en.words(w.lemma, pos=WN_POS[w.pos])
    if not words:
        return
    senses = words[0].senses()
    w.senses = len(senses)
    w.related.add(w.lemma)
    for s in senses:
        w.related.update(x.lower() for x in s.synset().lemmas())
    first = senses[0]
    w.lexfile = first.synset().lexfile() or ""
    # a synonym only when it is the MAIN sense of both words (big / large), not a rare one
    w.synonyms = set()
    for x in first.synset().lemmas():
        other = en.words(x, pos=WN_POS[w.pos])
        if (
            x.lower() != w.lemma
            and other
            and other[0].senses()
            and other[0].senses()[0].synset().id == first.synset().id
        ):
            w.synonyms.add(x.lower())
    for r in first.get_related("antonym"):
        lemma = r.word().lemma().lower()
        if zipf(lemma) >= 3.0:  # not "nondriver"
            w.antonyms.add(lemma)
    for s in senses[:3]:
        for r in s.get_related("derivation") + s.get_related("pertainym"):
            lemma = r.word().lemma().lower()
            pos = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}.get(
                r.word().pos
            )
            if pos and pos != w.pos and " " not in lemma:
                w.family.setdefault(pos, lemma)
    w.related |= w.antonyms | set(w.family.values())


def load_words(c1_count: int = 2600, log: Callable[[str], None] = print) -> list[Word]:
    data = json.loads((PROJECT_ROOT / "content/vocabulary/vocabulary.json").read_text())
    vi = vietnamese_meanings()
    words: list[Word] = []
    for item in data["items"]:
        if item.get("review_status") == "rejected" or " " in item["word"]:
            continue
        lemma = item["word"].lower()
        if not re.fullmatch(r"[a-z]+", lemma) or item["part_of_speech"] not in WN_POS:
            continue
        words.append(
            Word(
                item["id"],
                lemma,
                item["part_of_speech"],
                item["cefr_level"],
                item["definition"],
                item.get("example"),
            )
        )
    known = {w.lemma for w in words} | set(cefrj())
    en = wordnet()
    extra: list[tuple[float, Word]] = []
    for pos, wpos in WN_POS.items():
        for word in en.words(pos=wpos):
            lemma = word.lemma()
            if lemma in known or not re.fullmatch(r"[a-z]{4,}", lemma):
                continue
            z = zipf(lemma)
            if not 2.9 <= z <= 4.1:
                continue
            synset = word.senses()[0].synset()
            definition = synset.definition() or ""
            if not definition or len(definition) > 120 or not is_clean(definition + lemma):
                continue
            examples = [e for e in synset.examples() if lemma in e.lower()]
            extra.append(
                (
                    z,
                    Word(
                        f"{lemma}.{pos}.c1",
                        lemma,
                        pos,
                        "C1",
                        definition,
                        examples[0] if examples else None,
                    ),
                )
            )
            known.add(lemma)
    extra.sort(key=lambda x: -x[0])
    words += [w for _, w in extra[:c1_count]]
    for w in words:
        m = vi.get((w.lemma, w.pos))
        if m:
            w.vi, w.vi_sure, w.vi_all = m.text, m.sure, m.all
        _relations(w)
    log(
        f"  vocabulary: {len(words)} words, {sum(1 for w in words if w.vi)} with a Vietnamese "
        f"meaning ({sum(1 for w in words if w.vi_sure)} unambiguous), "
        f"{len(extra[:c1_count])} C1 words added"
    )
    return words


# --- corpus index: context sentences, word forms, collocations --------------------------------

LIGHT_VERBS = ("make", "do", "take", "have", "give", "get", "pay", "catch", "keep", "break")


@dataclass
class Usage:
    sentence: str
    start: int  # char offsets of the word in the sentence
    end: int
    tag: str  # Penn tag of the word as used
    source_ref: str


def corpus_index(docs: Iterator, targets: dict[tuple[str, str], Word], per_word: int = 4):
    """One pass over parsed sentences: example uses per (lemma, pos), light-verb + noun counts
    with an example sentence each."""
    spacy_pos = {"NOUN": "noun", "VERB": "verb", "ADJ": "adjective", "ADV": "adverb"}
    uses: dict[tuple[str, str], list[Usage]] = defaultdict(list)
    colloc: Counter = Counter()
    colloc_examples: dict[tuple[str, str], Usage] = {}
    for sentence, doc in docs:
        words = sum(1 for t in doc if not t.is_punct)
        if not 6 <= words <= 18:
            continue
        for t in doc:
            pos = spacy_pos.get(t.pos_)
            if pos:
                key = (t.lemma_.lower(), pos)
                if key in targets and len(uses[key]) < per_word and t.text.isalpha():
                    uses[key].append(
                        Usage(doc.text, t.idx, t.idx + len(t.text), t.tag_, sentence.ref)
                    )
            if t.dep_ == "dobj" and t.head.lemma_ in LIGHT_VERBS and t.pos_ == "NOUN":
                verb = t.head
                if verb.i < t.i and not any(c.dep_ == "neg" for c in verb.children):
                    pair = (verb.lemma_, t.lemma_.lower())
                    colloc[pair] += 1
                    if pair not in colloc_examples and verb.text.isalpha():
                        colloc_examples[pair] = Usage(
                            doc.text, verb.idx, verb.idx + len(verb.text), verb.tag_, sentence.ref
                        )
    return uses, colloc, colloc_examples


# --- question builders -----------------------------------------------------------------------


class Pools:
    def __init__(self, words: list[Word]) -> None:
        self.by_pos_level: dict[tuple[str, str], list[Word]] = defaultdict(list)
        for w in words:
            self.by_pos_level[(w.pos, w.level)].append(w)

    def distractors(
        self,
        target: Word,
        n: int,
        rng: random.Random,
        extra_ok: Callable[[Word], bool] = lambda _: True,
    ) -> list[Word]:
        rank = RANK[target.level]
        levels = [target.level] + [LEVELS5[r] for r in (rank - 1, rank + 1) if 0 <= r < 5]
        pool = [w for lvl in levels for w in self.by_pos_level.get((target.pos, lvl), [])]
        out: list[Word] = []
        for _ in range(60):
            if len(out) == n or not pool:
                break
            w = pool[rng.randrange(len(pool))]
            if (
                w.lemma in target.related
                or target.lemma in w.related
                or w in out
                or w.lemma[:4] == target.lemma[:4]
                or w.definition == target.definition
                or not extra_ok(w)
            ):
                continue
            out.append(w)
        return out if len(out) == n else []


def _src(ref: str = "", source_id: str = "oewn") -> SourceRef:
    licences = {"oewn": "CC BY 4.0 (Open English WordNet); CEFR-J Wordlist (cited)"}
    lic = licences.get(source_id) or sources.SOURCE_BY_ID[source_id].license
    return SourceRef(id=source_id, ref=ref, license=lic)


def _explain(w: Word) -> tuple[str, str]:
    en = f"'{w.lemma}' ({w.pos}) means: {w.definition}."
    if w.example:
        en += f" Example: {w.example}"
    vi = (
        f"'{w.lemma}' ({POS_VI[w.pos]}) nghĩa là: {w.vi}."
        if w.vi
        else f"'{w.lemma}' ({POS_VI[w.pos]}): {w.definition}."
    )
    return en, vi


def _common(w: Word, point: str, difficulty: str, quality: float) -> dict:
    return dict(
        skill="vocabulary",
        skill_id=f"vocabulary.{w.level.lower()}",
        level=w.level,
        topic=topic_of([w.lemma, *re.findall(r"[a-z]+", w.definition.lower())]),
        point=point,
        difficulty=difficulty,
        quality=quality,
    )


def word_questions(w: Word, pools: Pools, uses: list[Usage]) -> Iterator[QuestionRecord]:
    rng = random.Random(w.id)
    en, vi = _explain(w)
    # very polysemous words (thing, get, make): one English definition would test one sense
    # among many, so only the Vietnamese-meaning and in-context questions are made
    definable = w.senses < 8
    # 1) definition -> word
    d = pools.distractors(w, 3, rng) if definable else []
    if d:
        yield choice_question(
            qid=stable_id("vo.meaning", w.id),
            **_common(w, "meaning", "easy", 0.88),
            qtype="mcq",
            prompt=f"Which word means: “{w.definition}”?",
            instruction=f"Choose the {w.pos}.",
            right=w.lemma,
            wrong=[x.lemma for x in d],
            explanation=en,
            explanation_vi=vi,
            source=_src(w.id),
            tags=[w.pos],
        )
    # 2) word -> definition
    d = (
        pools.distractors(w, 3, rng, lambda x: abs(len(x.definition) - len(w.definition)) < 60)
        if definable
        else []
    )
    if d:
        yield choice_question(
            qid=stable_id("vo.definition", w.id),
            **_common(w, "definition", "easy", 0.86),
            qtype="mcq",
            prompt=f"What does “{w.lemma}” ({w.pos}) mean?",
            instruction="Choose the best definition.",
            right=w.definition,
            wrong=[x.definition for x in d],
            explanation=en,
            explanation_vi=vi,
            source=_src(w.id),
            tags=[w.pos],
        )
    # 3) Vietnamese meaning
    if w.vi_sure:
        # a distractor is never another meaning of the word ("bờ" is a meaning of "bank" too)
        d = pools.distractors(
            w, 3, rng, lambda x: x.vi_sure and x.vi.lower() not in w.vi_all | {w.vi.lower()}
        )
        if d:
            yield choice_question(
                qid=stable_id("vo.vietnamese", w.id),
                **_common(w, "vietnamese", "easy", 0.86),
                qtype="mcq",
                prompt=f"“{w.lemma}” ({w.pos}) nghĩa là gì?",
                instruction="Choose the Vietnamese meaning.",
                right=w.vi,
                wrong=[x.vi for x in d],
                explanation=en,
                explanation_vi=vi,
                source=_src(w.id, "viwiktionary"),
                tags=[w.pos, "vi"],
            )
    # 4) synonym
    # a synonym the learner can know: CEFR-J, same part of speech, up to B2
    syn = sorted(s for s in w.synonyms if learner_word(s, w.pos, "B2"))
    if syn:
        s = syn[0]
        d = pools.distractors(w, 3, rng, lambda x: s not in x.related)
        if d:
            yield choice_question(
                qid=stable_id("vo.synonym", w.id),
                **_common(w, "synonym", "medium", 0.84),
                qtype="mcq",
                prompt=f"Which word is closest in meaning to “{w.lemma}”?",
                instruction="Choose the synonym.",
                right=s,
                wrong=[x.lemma for x in d],
                explanation=f"'{s}' and '{w.lemma}' both mean: {w.definition}.",
                explanation_vi=f"'{s}' đồng nghĩa với '{w.lemma}'"
                + (f" ({w.vi})." if w.vi else "."),
                source=_src(w.id),
                tags=[w.pos],
            )
    # 5) antonym
    ant = sorted(a for a in w.antonyms if re.fullmatch(r"[a-z]+", a))
    if ant:
        a = ant[0]
        d = pools.distractors(w, 3, rng, lambda x: a not in x.related)
        if d:
            yield choice_question(
                qid=stable_id("vo.antonym", w.id),
                **_common(w, "antonym", "medium", 0.86),
                qtype="mcq",
                prompt=f"Which word is the opposite of “{w.lemma}”?",
                instruction="Choose the antonym.",
                right=a,
                wrong=[x.lemma for x in d],
                explanation=f"'{a}' is the opposite of '{w.lemma}' ({w.definition}).",
                explanation_vi=f"'{a}' trái nghĩa với '{w.lemma}'"
                + (f" ({w.vi})." if w.vi else "."),
                source=_src(w.id),
                tags=[w.pos],
            )
    # 6) word form (the word family) in a real sentence
    if uses and len(w.family) >= 2:
        u = uses[0]
        surface = u.sentence[u.start : u.end]
        if surface.lower() == w.lemma:
            forms = [f for f in w.family.values() if f != w.lemma]
            prompt = u.sentence[: u.start] + "___" + u.sentence[u.end :]
            yield choice_question(
                qid=stable_id("vo.word_form", w.id),
                **_common(w, "word_form", "medium", 0.82),
                qtype="mcq",
                prompt=prompt,
                instruction="Choose the correct word form.",
                right=surface,
                wrong=forms[:3],
                explanation=f"The gap needs a {w.pos}: '{surface}'. Other forms: "
                + ", ".join(f"{f} ({p})" for p, f in w.family.items())
                + ".",
                explanation_vi=f"Chỗ trống cần một {POS_VI[w.pos]}: '{surface}'.",
                source=_src(u.source_ref, "tatoeba-eng"),
                tags=[w.pos, "family"],
            )
    # 7) context (nouns and verbs: distractors from another semantic field)
    if uses and w.pos in ("noun", "verb"):
        u = uses[-1]
        surface = u.sentence[u.start : u.end]
        d = pools.distractors(w, 3, rng, lambda x: x.lexfile != w.lexfile)
        forms = [_inflect_like(x.lemma, surface, u.tag) for x in d]
        if d and all(forms):
            prompt = u.sentence[: u.start] + "___" + u.sentence[u.end :]
            yield choice_question(
                qid=stable_id("vo.context", w.id),
                **_common(w, "context", "hard", 0.76),
                qtype="mcq",
                prompt=prompt,
                instruction="Choose the word that fits the sentence.",
                right=surface,
                wrong=forms,
                explanation=en,
                explanation_vi=vi,
                source=_src(u.source_ref, "tatoeba-eng"),
                tags=[w.pos, "context"],
            )


def _inflect_like(lemma: str, surface: str, tag: str) -> str | None:
    from lemminflect import getInflection

    if tag in ("NN", "VB", "VBP", "JJ", "RB"):
        form = lemma
    else:
        forms = getInflection(lemma, tag)
        form = forms[0] if forms else None
    if form and surface[:1].isupper():
        form = form.capitalize()
    return form


def collocation_questions(colloc: Counter, examples: dict, level_of: Callable[[str], str]):
    """make/do/take... + noun where one verb is at least 85% of the corpus uses."""
    by_noun: dict[str, Counter] = defaultdict(Counter)
    for (verb, noun), n in colloc.items():
        by_noun[noun][verb] += n
    from lemminflect import getInflection

    for noun, verbs in sorted(by_noun.items()):
        total = sum(verbs.values())
        verb, n = verbs.most_common(1)[0]
        if total < 12 or n / total < 0.85 or not re.fullmatch(r"[a-z]+", noun):
            continue
        u = examples[(verb, noun)]
        surface = u.sentence[u.start : u.end]
        wrong_verbs = [
            v
            for v in ("make", "do", "take", "have", "give", "get")
            if v != verb and verbs.get(v, 0) == 0
        ][:3]
        forms = []
        for v in wrong_verbs:
            f = v if u.tag in ("VB", "VBP") else (getInflection(v, u.tag) or [None])[0]
            forms.append(f.capitalize() if f and surface[:1].isupper() else f)
        if len(forms) < 3 or not all(forms):
            continue
        level = max(level_of(noun), "A2", key=RANK.__getitem__)
        yield choice_question(
            qid=stable_id("vo.collocation", verb, noun),
            skill="vocabulary",
            skill_id=f"vocabulary.{level.lower()}",
            level=level,
            topic=topic_of([noun]),
            point="collocation",
            difficulty="medium",
            qtype="mcq",
            prompt=u.sentence[: u.start] + "___" + u.sentence[u.end :],
            instruction="Choose the verb that goes with the noun.",
            right=surface,
            wrong=forms,
            explanation=f"We say '{verb} a/the {noun}' ({n} of {total} uses in our corpus). "
            f"It is a fixed collocation.",
            explanation_vi=f"Cụm cố định: '{verb} ... {noun}' (collocation).",
            source=_src(u.source_ref, "tatoeba-eng"),
            quality=0.84,
            tags=[f"verb:{verb}"],
        )


def matching_questions(words: list[Word], size: int = 4) -> Iterator[QuestionRecord]:
    """Four words of one level and part of speech with their definitions."""
    groups: dict[tuple[str, str], list[Word]] = defaultdict(list)
    for w in words:
        groups[(w.level, w.pos)].append(w)
    for (level, pos), ws in sorted(groups.items()):
        rng = random.Random(f"{level}{pos}")
        ws = sorted(ws, key=lambda w: w.id)
        rng.shuffle(ws)
        for i in range(0, len(ws) - size + 1, size):
            group = ws[i : i + size]
            lemmas = {w.lemma for w in group}
            if any(w.related & (lemmas - {w.lemma}) for w in group):
                continue
            right_ids = "abcdefgh"[:size]
            order = list(range(size))
            rng.shuffle(order)
            options = [
                OptionRecord(id=right_ids[k], text=group[j].definition) for k, j in enumerate(order)
            ]
            pairs = {f"l{j}": right_ids[order.index(j)] for j in range(size)}
            left = [{"id": f"l{j}", "text": group[j].lemma} for j in range(size)]
            yield QuestionRecord(
                id=stable_id("vo.matching", *sorted(lemmas)),
                skill="vocabulary",
                skill_id=f"vocabulary.{level.lower()}",
                level=level,
                topic="daily_life",
                point="matching",
                difficulty="medium",
                qtype="matching",
                instruction="Match each word with its meaning.",
                prompt=f"Match the {pos}s with their definitions.",
                options=options,
                answer={"pairs": pairs},
                display={"left": left},
                explanation=" ".join(f"{w.lemma}: {w.definition}." for w in group),
                explanation_vi=" ".join(f"{w.lemma}: {w.vi}." for w in group if w.vi),
                source=_src(),
                status=BankStatus.VALIDATED,
                quality=0.8,
                tags=[pos],
            )
