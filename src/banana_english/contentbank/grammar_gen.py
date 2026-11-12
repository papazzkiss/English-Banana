"""Grammar questions from real sentences (Tatoeba, Wikipedia), one detector per grammar point.

Every detector only fires where exactly one option is right:
  * tense choice needs a time signal that rules the distractor tenses out (yesterday -> past
    simple; the distractors are tenses that are wrong with "yesterday", never ones that could
    also fit, like the past continuous);
  * form questions keep the tense and vary agreement or verb form (has gone / have gone /
    has went), so only one form is grammatical;
  * typed answers name the tense in the instruction, so the answer is unique.
The original sentence is always the right answer: it was written by a person.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from banana_english.contentbank.lexicon import (
    length_level,
    level_of_words,
    max_level,
    topic_of,
)

POINT_LEVEL = {
    "present_simple": "A1",
    "present_continuous": "A1",
    "past_simple": "A1",
    "present_perfect": "A2",
    "past_continuous": "A2",
    "past_perfect": "B1",
    "future_will": "A2",
    "modals": "A2",
    "conditionals": "B1",
    "passive": "B1",
    "relative_clauses": "B1",
    "articles": "A1",
    "prepositions_time": "A1",
    "comparatives": "A2",
    "superlatives": "A2",
    "gerunds_infinitives": "B1",
    "subject_verb_agreement": "A1",
    "there_be": "A1",
    "questions_do": "A1",
    "quantifiers": "A2",
    "reflexive_pronouns": "A2",
    "possessives": "A1",
    "adjectives_adverbs": "A2",
    "contrast_linkers": "B2",
    "word_order": "A1",
}


@dataclass
class Candidate:
    point: str
    qtype: str  # mcq | fill_blank | error_id | ordering
    prompt: str
    instruction: str
    explanation: str
    explanation_vi: str
    options: list[str] = field(default_factory=list)  # [0] is the right one (shuffled later)
    accepted: list[str] = field(default_factory=list)
    pieces: list[str] = field(default_factory=list)
    base_quality: float = 0.8
    tags: list[str] = field(default_factory=list)


@dataclass
class GrammarItem:
    candidate: Candidate
    level: str
    topic: str
    difficulty: str
    sentence_id: str
    source: str
    ref: str
    quality: float


# --- verb forms --------------------------------------------------------------------------------


def inflect(lemma: str, tag: str) -> str | None:
    from lemminflect import getInflection

    if lemma == "be":
        return {"VBZ": "is", "VBD": "was", "VBN": "been", "VBG": "being", "VB": "be"}.get(tag)
    forms = getInflection(lemma, tag)
    return forms[0] if forms else None


# Verbs with two accepted past participles (got/gotten, learned/learnt...): a "wrong
# participle" distractor could be right, so these are left out of form questions.
TWO_PARTICIPLES = {
    "get",
    "prove",
    "learn",
    "dream",
    "burn",
    "spell",
    "smell",
    "spill",
    "spoil",
    "leap",
    "kneel",
    "dwell",
    "sew",
    "show",
    "swell",
    "mow",
    "saw",
    "strive",
    "dive",
    "wake",
    "shine",
    "speed",
    "light",
    "knit",
    "wed",
    "bet",
    "bid",
    "fit",
    "quit",
    "wet",
    "lean",
    "earn",
    "forecast",
    "broadcast",
    "sneak",
    "plead",
}
# Verbs that are also intransitive with the same subject (the door opened): an active
# distractor would be right too, so they get no passive questions.
ERGATIVE = {
    "fill",
    "open",
    "close",
    "shut",
    "break",
    "change",
    "move",
    "sell",
    "start",
    "stop",
    "begin",
    "end",
    "finish",
    "increase",
    "decrease",
    "grow",
    "improve",
    "burn",
    "cook",
    "melt",
    "freeze",
    "drop",
    "split",
    "turn",
    "roll",
    "shake",
    "spread",
    "develop",
    "run",
    "tear",
    "crack",
    "bend",
    "boil",
    "dry",
    "empty",
    "sink",
    "float",
    "slide",
    "spin",
    "stretch",
    "wake",
    "wash",
    "bounce",
    "collapse",
    "divide",
    "double",
    "expand",
    "fade",
    "fly",
    "gather",
    "hang",
    "join",
    "land",
    "light",
    "mix",
    "reverse",
    "separate",
    "shrink",
    "slow",
    "sound",
    "stand",
    "unite",
    "vary",
    "weaken",
    "pay",
    "read",
    "photograph",
    "translate",
    "wear",
    "clean",
    "cut",
    "print",
    "iron",
}

COLLECTIVE = {
    "team",
    "family",
    "government",
    "staff",
    "company",
    "firm",
    "police",
    "crew",
    "class",
    "committee",
    "audience",
    "band",
    "crowd",
    "group",
    "jury",
    "army",
    "public",
    "club",
    "council",
    "management",
    "department",
    "board",
    "orchestra",
    "choir",
    "majority",
    "minority",
    "couple",
    "pair",
    "number",
    "series",
    "news",
    "data",
    "media",
    "people",
    "cattle",
}

_PRONOUN_PERSON = {
    "i": "1s",
    "you": "2",
    "he": "3s",
    "she": "3s",
    "it": "3s",
    "we": "p",
    "they": "p",
    "this": "3s",
    "that": "3s",
    "these": "p",
    "those": "p",
    "everyone": "3s",
    "somebody": "3s",
    "someone": "3s",
    "everybody": "3s",
    "nobody": "3s",
    "nothing": "3s",
    "everything": "3s",
}


def person_of(subject) -> str | None:
    """1s, 2, 3s or p for a subject token, None when unclear (coordinated, clauses...)."""
    if subject is None or any(c.dep_ == "cc" or c.dep_ == "conj" for c in subject.children):
        return None
    low = subject.lower_
    if subject.lemma_.lower() in COLLECTIVE:
        return None  # "the team is / are": both accepted in British English
    if low in _PRONOUN_PERSON:
        return _PRONOUN_PERSON[low]
    if subject.tag_ in ("NN", "NNP"):
        return "3s"
    if subject.tag_ in ("NNS", "NNPS"):
        return "p"
    return None


def be_form(person: str, past: bool) -> str:
    if past:
        return "were" if person in ("2", "p") else "was"
    return {"1s": "am", "2": "are", "3s": "is", "p": "are"}[person]


def have_form(person: str) -> str:
    return "has" if person == "3s" else "have"


def tense_form(tense: str, lemma: str, person: str) -> str | None:
    vbz, vbd, vbn, vbg = (inflect(lemma, t) for t in ("VBZ", "VBD", "VBN", "VBG"))
    if None in (vbz, vbd, vbn, vbg):
        return None
    if lemma == "be":
        present = be_form(person, past=False)
        past = be_form(person, past=True)
        return {
            "present_simple": present,
            "past_simple": past,
            "present_perfect": f"{have_form(person)} been",
            "past_perfect": "had been",
            "future_will": "will be",
            "present_continuous": f"{present} being",
            "past_continuous": f"{past} being",
        }.get(tense)
    return {
        "present_simple": vbz if person == "3s" else lemma,
        "present_continuous": f"{be_form(person, False)} {vbg}",
        "past_simple": vbd,
        "past_continuous": f"{be_form(person, True)} {vbg}",
        "present_perfect": f"{have_form(person)} {vbn}",
        "past_perfect": f"had {vbn}",
        "future_will": f"will {lemma}",
    }.get(tense)


def contractions(form: str) -> list[str]:
    out = [form]
    for full, short in (
        ("has ", "'s "),
        ("have ", "'ve "),
        ("will ", "'ll "),
        ("had ", "'d "),
        ("am ", "'m "),
        ("is ", "'s "),
        ("are ", "'re "),
    ):
        if form.startswith(full):
            out.append(short + form[len(full) :])
    return out


# --- time signals: which tenses they allow, which they rule out ----------------------------------

TENSES = (
    "present_simple",
    "present_continuous",
    "past_simple",
    "past_continuous",
    "present_perfect",
    "past_perfect",
    "future_will",
)
TENSE_NAME = {
    "present_simple": ("present simple", "hiện tại đơn"),
    "present_continuous": ("present continuous", "hiện tại tiếp diễn"),
    "past_simple": ("past simple", "quá khứ đơn"),
    "past_continuous": ("past continuous", "quá khứ tiếp diễn"),
    "present_perfect": ("present perfect", "hiện tại hoàn thành"),
    "past_perfect": ("past perfect", "quá khứ hoàn thành"),
    "future_will": ("future with will", "tương lai đơn (will)"),
}


@dataclass(frozen=True)
class Signal:
    pattern: re.Pattern
    tense: str
    wrong: tuple[str, ...]  # tenses that are clearly wrong with this signal
    why_en: str
    why_vi: str


def _sig(regex: str, tense: str, wrong: tuple[str, ...], en: str, vi: str) -> Signal:
    return Signal(re.compile(regex, re.I), tense, wrong, en, vi)


SIGNALS = (
    _sig(
        r"\b(yesterday|\d+ (days?|weeks?|months?|years?|hours?|minutes?) ago|last "
        r"(night|week|month|year|summer|winter|spring|autumn|monday|tuesday|wednesday|"
        r"thursday|friday|saturday|sunday|weekend|time))\b",
        "past_simple",
        ("present_simple", "present_perfect", "future_will", "present_continuous"),
        "'{sig}' refers to a finished time in the past, so we use the past simple: {ans}.",
        "'{sig}' chỉ một thời điểm đã kết thúc trong quá khứ nên dùng quá khứ đơn: {ans}.",
    ),
    _sig(
        r"\bsince (19|20)\d\d\b|\bsince (monday|tuesday|wednesday|thursday|friday|saturday|"
        r"sunday|january|february|march|april|may|june|july|august|september|october|"
        r"november|december|last \w+|yesterday|then|childhood)\b",
        "present_perfect",
        ("past_simple", "present_simple", "future_will", "present_continuous"),
        "'{sig}' shows a period that started in the past and continues now, so we use the "
        "present perfect: {ans}.",
        "'{sig}' chỉ khoảng thời gian bắt đầu trong quá khứ và kéo dài đến hiện tại nên dùng "
        "hiện tại hoàn thành: {ans}.",
    ),
    _sig(
        r"\b(tomorrow|next (week|month|year|monday|tuesday|wednesday|thursday|friday|"
        r"saturday|sunday|weekend|summer|time))\b",
        "future_will",
        ("past_simple", "present_perfect", "past_perfect", "past_continuous"),
        "'{sig}' refers to the future, so we use will + base form: {ans}.",
        "'{sig}' chỉ tương lai nên dùng will + động từ nguyên mẫu: {ans}.",
    ),
    _sig(
        r"^(look|listen)!|\b(at the moment|at present|currently)\b",
        "present_continuous",
        ("past_simple", "present_perfect", "past_perfect"),
        "'{sig}' shows the action is happening now, so we use the present continuous: {ans}.",
        "'{sig}' cho thấy hành động đang diễn ra nên dùng hiện tại tiếp diễn: {ans}.",
    ),
    _sig(
        r"\bby the time\b",
        "past_perfect",
        ("present_perfect", "present_simple", "future_will"),
        "With '{sig}' + past simple, the earlier action takes the past perfect: {ans}.",
        "Với '{sig}' + quá khứ đơn, hành động xảy ra trước dùng quá khứ hoàn thành: {ans}.",
    ),
    _sig(
        r"\bwhile\b",
        "past_continuous",
        ("present_continuous", "present_perfect", "future_will"),
        "'{sig}' + a past action in progress takes the past continuous: {ans}.",
        "'{sig}' + hành động đang diễn ra trong quá khứ dùng quá khứ tiếp diễn: {ans}.",
    ),
)


# --- verb group detection -------------------------------------------------------------------------


@dataclass(frozen=True)
class VerbGroup:
    start: int  # token index of the first word of the group
    end: int  # index of the main verb
    tense: str
    lemma: str
    person: str
    subject: object


def _verb_group(doc) -> VerbGroup | None:
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is None or root.pos_ not in ("VERB", "AUX") or doc[-1].text == "?":
        return None
    if any(c.dep_ == "neg" for c in root.children):
        return None
    auxes = sorted((c for c in root.children if c.dep_ in ("aux", "auxpass")), key=lambda t: t.i)
    if any(a.i > root.i for a in auxes) or any(c.dep_ == "auxpass" for c in root.children):
        return None
    subject = next((c for c in root.children if c.dep_ == "nsubj"), None)
    person = person_of(subject)
    if person is None or subject.i > (auxes[0].i if auxes else root.i):
        return None
    start = auxes[0].i if auxes else root.i
    if any(t.pos_ != "AUX" and t.i != root.i for t in doc[start : root.i + 1]):
        return None  # an adverb inside the group (has already gone): skip
    words = [a.lower_ for a in auxes]
    lemma = root.lemma_.lower()
    tag = root.tag_
    if not re.fullmatch(r"[a-z]+", lemma):
        return None
    tense = None
    if not words and tag in ("VBZ", "VBP"):
        tense = "present_simple"
    elif not words and tag == "VBD":
        tense = "past_simple"
    elif words in (["am"], ["is"], ["are"], ["'m"], ["'s"], ["'re"]) and tag == "VBG":
        tense = "present_continuous"
    elif words in (["was"], ["were"]) and tag == "VBG":
        tense = "past_continuous"
    elif words in (["has"], ["have"], ["'ve"]) and tag == "VBN":
        tense = "present_perfect"
    elif words in (["had"], ["'d"]) and tag == "VBN":
        tense = "past_perfect"
    elif words in (["will"], ["'ll"]) and tag == "VB":
        tense = "future_will"
    if tense is None or lemma in ("be", "have") and tense != "present_simple":
        return None
    if doc[start].text.startswith("'"):  # contracted aux: the blank would eat the subject's 's
        return None
    return VerbGroup(start, root.i, tense, lemma, person, subject)


def _blanked(doc, start: int, end: int, hint: str | None = None) -> str:
    """The sentence with tokens start..end replaced by ___ (and an optional (hint))."""
    before = doc[:start].text_with_ws if start else ""
    after = doc[end + 1 :].text_with_ws if end + 1 < len(doc) else ""
    blank = "___" + (f" ({hint})" if hint else "")
    sep = " " if doc[end].whitespace_ else ""
    return (before + blank + sep + after).strip()


# --- detectors ----------------------------------------------------------------------------------


def tense_items(doc) -> Iterator[Candidate]:
    g = _verb_group(doc)
    if g is None:
        return
    right = doc[g.start : g.end + 1].text
    expected = tense_form(g.tense, g.lemma, g.person)
    if expected is None or expected.lower() != right.lower():
        return  # our inflection disagrees with the sentence: do not risk it
    text = doc.text
    en_t, vi_t = TENSE_NAME[g.tense]
    # 1) tense choice, only with a signal that rules the distractors out
    for s in SIGNALS:
        m = s.pattern.search(text)
        if not m or s.tense != g.tense:
            continue
        distractors = [tense_form(t, g.lemma, g.person) for t in s.wrong]
        distractors = [d for d in dict.fromkeys(distractors) if d and d.lower() != right.lower()]
        if len(distractors) < 3:
            break
        sig = m.group(0).strip("!").lower()
        yield Candidate(
            g.tense,
            "mcq",
            _blanked(doc, g.start, g.end, g.lemma),
            "Choose the correct form of the verb in brackets.",
            s.why_en.format(sig=sig, ans=right),
            s.why_vi.format(sig=sig, ans=right),
            options=[right, *distractors[:3]],
            base_quality=0.86,
            tags=[f"signal:{sig}"],
        )
        # 1b) the same as a typed answer: the instruction names the tense, so it is unique
        yield Candidate(
            g.tense,
            "fill_blank",
            _blanked(doc, g.start, g.end, g.lemma),
            f"Complete the sentence. Use the {en_t} of the verb in brackets.",
            s.why_en.format(sig=sig, ans=right),
            s.why_vi.format(sig=sig, ans=right),
            accepted=contractions(right),
            base_quality=0.84,
            tags=[f"signal:{sig}", "typed"],
        )
        break
    # 2) form: same tense, wrong agreement / wrong verb form
    wrong = _form_distractors(g, right)
    if len(wrong) >= 3:
        yield Candidate(
            g.tense,
            "mcq",
            _blanked(doc, g.start, g.end, g.lemma),
            f"Choose the correct {en_t} form.",
            f"The subject is '{g.subject.text}', so the {en_t} form is '{right}'.",
            f"Chủ ngữ là '{g.subject.text}' nên dạng {vi_t} đúng là '{right}'.",
            options=[right, *wrong[:3]],
            base_quality=0.88,
            tags=["form"],
        )


def _form_distractors(g: VerbGroup, right: str) -> list[str]:
    if g.lemma in TWO_PARTICIPLES:
        return []
    # agreement error: singular subject gets the plural form and the other way round
    other = "p" if g.person in ("1s", "3s") else "3s"
    vbd, vbn, vbg = (inflect(g.lemma, t) for t in ("VBD", "VBN", "VBG"))
    candidates: list[str | None] = [tense_form(g.tense, g.lemma, other)]
    if g.tense == "present_perfect":
        candidates += [
            f"{have_form(g.person)} {vbd}" if vbd != vbn else None,
            f"{have_form(g.person)} {g.lemma}",
            f"{have_form(g.person)} {vbg}",
        ]
    elif g.tense == "past_perfect":
        candidates += [f"had {vbd}" if vbd != vbn else None, f"had {g.lemma}", f"had {vbg}"]
    elif g.tense in ("present_continuous", "past_continuous"):
        be = right.split()[0]
        candidates += [f"{be} {g.lemma}", vbg]
    elif g.tense == "future_will":
        candidates += [f"will {inflect(g.lemma, 'VBZ')}", f"will {vbg}", f"will to {g.lemma}"]
    elif g.tense == "past_simple":
        if vbd == g.lemma:  # put/cut/set: did put, was put, has put are all grammatical
            return []
        # never "was + base" when the base is also the participle (was read: passive)
        be_wrong = f"was {g.lemma}" if g.person not in ("p", "2") else f"were {g.lemma}"
        candidates = [
            f"did {vbd}",
            f"{have_form(g.person)} {g.lemma}",
            be_wrong if g.lemma != vbn else None,
            vbn if vbn not in (vbd, g.lemma) else None,
        ]
    elif g.tense == "present_simple":
        candidates += [vbg, f"{be_form(g.person, False)} {g.lemma}", vbd and f"do {g.lemma}"]
    out: list[str] = []
    for c in candidates:
        if c and c.lower() != right.lower() and c not in out:
            out.append(c)
    return out


_AN_WORD = re.compile(r"^(hour|honest|honou?r|heir)", re.I)
_A_VOWEL = re.compile(r"^(uni|use|usu|uti|eu|one|once|ewe|u[bcfgklmrst][aeiou])", re.I)


def article_items(doc) -> Iterator[Candidate]:
    for t in doc:
        if t.lower_ not in ("a", "an") or t.dep_ != "det" or t.i + 1 >= len(doc):
            continue
        nxt = doc[t.i + 1]
        if not nxt.is_alpha:
            continue
        vowel_sound = (nxt.lower_[0] in "aeiou" and not _A_VOWEL.match(nxt.lower_)) or bool(
            _AN_WORD.match(nxt.lower_)
        )
        if (t.lower_ == "an") != vowel_sound:
            continue  # the sentence breaks our rule (acronyms, rare words): skip
        right = t.text if t.i else t.text.lower()
        wrong = "an" if right.lower() == "a" else "a"
        rule_en = (
            "'{w}' starts with a vowel sound, so we use 'an'."
            if right.lower() == "an"
            else "'{w}' starts with a consonant sound, so we use 'a'."
        )
        rule_vi = (
            "'{w}' bắt đầu bằng nguyên âm (âm đọc) nên dùng 'an'."
            if right.lower() == "an"
            else "'{w}' bắt đầu bằng phụ âm (âm đọc) nên dùng 'a'."
        )
        special = bool(_AN_WORD.match(nxt.lower_) or _A_VOWEL.match(nxt.lower_))
        if special:
            rule_en += " What counts is the sound, not the letter."
            rule_vi += " Quan trọng là âm đọc, không phải chữ cái."
        prompt = _blanked(doc, t.i, t.i)
        if t.i == 0:
            prompt = "___" + prompt[3:]
            right, wrong = right.capitalize(), wrong.capitalize()
        yield Candidate(
            "articles",
            "mcq",
            prompt,
            "Choose a or an.",
            rule_en.format(w=nxt.text),
            rule_vi.format(w=nxt.text),
            options=[right, wrong],
            base_quality=0.9 if not special else 0.93,
            tags=["a_an", "special" if special else "regular"],
        )
        return


_DAYS = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?"
_MONTHS = r"(january|february|march|april|may|june|july|august|september|october|november|december)"
TIME_PREPS = (
    (re.compile(rf"^{_DAYS}$", re.I), "on", "days of the week", "các ngày trong tuần"),
    (re.compile(rf"^{_MONTHS}$", re.I), "in", "months", "các tháng"),
    (re.compile(r"^(1[5-9]|20)\d\d$"), "in", "years", "các năm"),
    (re.compile(r"^(\d{1,2}(:\d\d)?|noon|midnight)$", re.I), "at", "clock times", "giờ cụ thể"),
    (re.compile(r"^(spring|summer|autumn|winter)$", re.I), "in", "seasons", "các mùa"),
    (re.compile(r"^night$", re.I), "at", "'night'", "'night'"),
    (re.compile(r"^(christmas|easter)$", re.I), "at", "holiday periods", "các dịp lễ"),
)
_PARTS_OF_DAY = re.compile(r"^(morning|afternoon|evening)$", re.I)


def preposition_items(doc) -> Iterator[Candidate]:
    for t in doc:
        if t.lower_ not in ("in", "on", "at") or t.dep_ != "prep":
            continue
        obj = next((c for c in t.children if c.dep_ == "pobj"), None)
        if (
            obj is None
            or obj.i != t.i + 1
            and not (obj.i == t.i + 2 and doc[t.i + 1].lower_ == "the")
        ):
            continue
        rule = None
        if obj.i == t.i + 2 and _PARTS_OF_DAY.match(obj.text) and t.lower_ == "in":
            rule = (
                "in",
                "parts of the day (in the morning)",
                "các buổi trong ngày (in the morning)",
            )
        else:
            for pattern, prep, what_en, what_vi in TIME_PREPS:
                if obj.i == t.i + 1 and pattern.match(obj.text):
                    rule = (prep, what_en, what_vi)
                    break
        if rule is None or rule[0] != t.lower_:
            continue
        prep, what_en, what_vi = rule
        yield Candidate(
            "prepositions_time",
            "mcq",
            _blanked(doc, t.i, t.i),
            "Choose the correct preposition of time.",
            f"We use '{prep}' with {what_en}: {prep} {doc[t.i + 1 : obj.i + 1].text}.",
            f"Dùng '{prep}' với {what_vi}: {prep} {doc[t.i + 1 : obj.i + 1].text}.",
            options=[prep, *[p for p in ("in", "on", "at") if p != prep]],
            base_quality=0.88,
            tags=[f"prep:{prep}"],
        )
        return


def comparison_items(doc) -> Iterator[Candidate]:
    for t in doc:
        if t.tag_ == "JJR" and t.i + 1 < len(doc) and doc[t.i + 1].lower_ == "than":
            base = t.lemma_.lower()
            if not re.fullmatch(r"[a-z]+", base) or base in (
                "more",
                "less",
                "good",
                "bad",
                "far",
                "much",
                "many",
                "little",
            ):
                continue
            right = t.text
            if right.lower().startswith("more"):
                continue
            wrong = [f"more {base}", f"{inflect(base, 'JJS') or base + 'est'}", f"more {right}"]
            yield Candidate(
                "comparatives",
                "mcq",
                _blanked(doc, t.i, t.i, base),
                "Choose the correct comparative.",
                f"'than' needs a comparative. '{base}' is short, so we add -er: {right}.",
                f"Sau đó là 'than' nên dùng so sánh hơn. '{base}' là tính từ ngắn nên thêm -er: "
                f"{right}.",
                options=[right, *wrong],
                base_quality=0.88,
                tags=["short_adj"],
            )
            return
        if (
            t.lower_ == "more"
            and t.i + 2 < len(doc)
            and doc[t.i + 1].tag_ == "JJ"
            and doc[t.i + 2].lower_ == "than"
        ):
            adj = doc[t.i + 1].text
            if not re.fullmatch(r"[a-z]+", adj) or len(adj) < 6:
                continue
            yield Candidate(
                "comparatives",
                "mcq",
                _blanked(doc, t.i, t.i + 1, adj),
                "Choose the correct comparative.",
                f"'{adj}' is a long adjective, so the comparative is 'more {adj}'.",
                f"'{adj}' là tính từ dài nên so sánh hơn là 'more {adj}'.",
                options=[f"more {adj}", f"{adj}er", f"most {adj}", f"more {adj}er"],
                base_quality=0.86,
                tags=["long_adj"],
            )
            return
        if t.tag_ == "JJS" and t.i > 0 and doc[t.i - 1].lower_ == "the":
            base = t.lemma_.lower()
            if not re.fullmatch(r"[a-z]+", base) or base in (
                "most",
                "least",
                "good",
                "bad",
                "far",
                "many",
                "much",
                "little",
            ):
                continue
            right = t.text
            yield Candidate(
                "superlatives",
                "mcq",
                _blanked(doc, t.i, t.i, base),
                "Choose the correct superlative.",
                f"'the' + a short adjective + -est makes the superlative: the {right}.",
                f"Cấu trúc so sánh nhất với tính từ ngắn: the + tính từ + -est: the {right}.",
                options=[
                    right,
                    inflect(base, "JJR") or base + "er",
                    f"most {base}",
                    f"most {right}",
                ],
                base_quality=0.86,
            )
            return


GERUND_VERBS = {
    "enjoy",
    "finish",
    "avoid",
    "mind",
    "suggest",
    "keep",
    "consider",
    "practise",
    "practice",
    "miss",
    "imagine",
    "deny",
    "admit",
    "risk",
    "quit",
}
INFINITIVE_VERBS = {
    "want",
    "decide",
    "hope",
    "plan",
    "promise",
    "agree",
    "refuse",
    "expect",
    "learn",
    "manage",
    "offer",
    "afford",
    "choose",
    "pretend",
    "fail",
    "intend",
    "seem",
    "wish",
    "deserve",
    "threaten",
}


def gerund_infinitive_items(doc) -> Iterator[Candidate]:
    for t in doc:
        lemma = t.lemma_.lower()
        if t.pos_ != "VERB" or lemma not in GERUND_VERBS | INFINITIVE_VERBS:
            continue
        comp = next((c for c in t.children if c.dep_ == "xcomp"), None)
        if comp is None or comp.i != t.i + (2 if lemma in INFINITIVE_VERBS else 1):
            continue
        vlemma = comp.lemma_.lower()
        if not re.fullmatch(r"[a-z]+", vlemma):
            continue
        ing = inflect(vlemma, "VBG")
        if lemma in GERUND_VERBS and comp.tag_ == "VBG":
            right, start = comp.text, comp.i
            why_en = f"'{t.text}' is followed by the -ing form: {t.text} {right}."
            why_vi = f"Sau '{t.text}' dùng động từ dạng -ing: {t.text} {right}."
        elif lemma in INFINITIVE_VERBS and comp.tag_ == "VB" and doc[t.i + 1].lower_ == "to":
            right, start = f"to {comp.text}", t.i + 1
            why_en = f"'{t.text}' is followed by to + base form: {t.text} {right}."
            why_vi = f"Sau '{t.text}' dùng to + động từ nguyên mẫu: {t.text} {right}."
        else:
            continue
        options = [
            right,
            *[o for o in (ing, f"to {vlemma}", vlemma, f"to {ing}") if o and o != right],
        ]
        yield Candidate(
            "gerunds_infinitives",
            "mcq",
            _blanked(doc, start, comp.i, vlemma),
            "Choose the correct form: -ing or to + verb.",
            why_en,
            why_vi,
            options=options[:4],
            base_quality=0.87,
            tags=[f"verb:{lemma}"],
        )
        return


_MODALS = {"can", "could", "must", "should", "might", "may", "would"}


def modal_items(doc) -> Iterator[Candidate]:
    for t in doc:
        if t.lower_ not in _MODALS or t.dep_ != "aux" or t.i + 1 >= len(doc):
            continue
        verb = doc[t.i + 1]
        if verb.head.i != verb.i or verb.tag_ != "VB" or t.head.i != verb.i:
            continue
        lemma = verb.lemma_.lower()
        if not re.fullmatch(r"[a-z]+", lemma) or lemma == "be":
            continue
        wrong = [f"to {lemma}", inflect(lemma, "VBZ"), inflect(lemma, "VBG")]
        yield Candidate(
            "modals",
            "mcq",
            _blanked(doc, verb.i, verb.i, lemma),
            "Choose the correct verb form after the modal verb.",
            f"After a modal verb like '{t.lower_}' we use the base form without 'to': "
            f"{t.lower_} {verb.text}.",
            f"Sau động từ khuyết thiếu '{t.lower_}' dùng động từ nguyên mẫu không 'to': "
            f"{t.lower_} {verb.text}.",
            options=[verb.text, *[w for w in wrong if w]],
            base_quality=0.9,
            tags=[f"modal:{t.lower_}"],
        )
        return


def passive_items(doc) -> Iterator[Candidate]:
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is None or root.tag_ != "VBN":
        return
    auxpass = [c for c in root.children if c.dep_ == "auxpass"]
    aux = [c for c in root.children if c.dep_ == "aux"]
    subj = next((c for c in root.children if c.dep_ == "nsubjpass"), None)
    if len(auxpass) != 1 or aux or subj is None or any(c.dep_ == "neg" for c in root.children):
        return
    be = auxpass[0]
    if be.i + 1 != root.i or be.lower_ not in ("is", "are", "was", "were"):
        return
    lemma = root.lemma_.lower()
    person = person_of(subj)
    if person is None or not re.fullmatch(r"[a-z]+", lemma) or lemma in ERGATIVE:
        return
    right = f"{be.text} {root.text}"
    past = be.lower_ in ("was", "were")
    vbd, vbg = inflect(lemma, "VBD"), inflect(lemma, "VBG")
    wrong = [
        vbd if past else inflect(lemma, "VBZ" if person == "3s" else "VB") or lemma,
        f"{be.text} {vbg}",
        f"{be.text} {lemma}",
    ]
    by = any(c.dep_ == "agent" for c in root.children)
    yield Candidate(
        "passive",
        "mcq",
        _blanked(doc, be.i, root.i, lemma),
        "Choose the correct form of the verb in brackets.",
        f"The subject '{subj.text}' receives the action{' (by ... says who does it)' if by else ''}"
        f", so we use the passive: be + past participle ({right}).",
        f"Chủ ngữ '{subj.text}' là đối tượng chịu tác động nên dùng bị động: be + quá khứ phân "
        f"từ ({right}).",
        options=[right, *[w for w in wrong if w and w.lower() != right.lower()]],
        base_quality=0.85,
        tags=["past" if past else "present"],
    )


_PERSON_NOUNS = {
    "man",
    "woman",
    "boy",
    "girl",
    "person",
    "people",
    "friend",
    "teacher",
    "student",
    "doctor",
    "child",
    "children",
    "men",
    "women",
    "boys",
    "girls",
    "guy",
    "lady",
    "neighbor",
    "neighbour",
    "brother",
    "sister",
    "mother",
    "father",
    "son",
    "daughter",
    "writer",
    "artist",
    "player",
    "customer",
    "driver",
    "nurse",
    "worker",
    "someone",
    "somebody",
    "anyone",
    "everyone",
}


def relative_items(doc) -> Iterator[Candidate]:
    for t in doc:
        if t.lower_ not in ("who", "which") or t.dep_ not in ("nsubj", "dobj", "nsubjpass"):
            continue
        if t.i + 1 < len(doc) and doc[t.i + 1].text.startswith("'"):
            continue  # who's / which's: the blank would split the contraction
        clause = t.head
        if clause.dep_ != "relcl":
            continue
        antecedent = clause.head
        person = antecedent.lower_ in _PERSON_NOUNS or antecedent.ent_type_ == "PERSON"
        if (t.lower_ == "who") != person:
            continue
        right = t.lower_
        yield Candidate(
            "relative_clauses",
            "mcq",
            _blanked(doc, t.i, t.i),
            "Choose the correct relative pronoun.",
            f"'{antecedent.text}' is {'a person' if person else 'a thing'}, so we use '{right}'.",
            f"'{antecedent.text}' là {'người' if person else 'vật'} nên dùng '{right}'.",
            options=[right, "which" if right == "who" else "who", "whose", "where"],
            base_quality=0.84,
            tags=["person" if person else "thing"],
        )
        return


def agreement_items(doc) -> Iterator[Candidate]:
    """is/are, was/were, has/have, does/do and there is/are, from clear subjects."""
    if len(doc) > 2 and doc[0].lower_ in ("do", "does") and doc[-1].text == "?":
        subj = next((c for c in doc[0].head.children if c.dep_ == "nsubj"), None)
        person = person_of(subj)
        if person and subj.i in (1, 2):
            right = "Does" if person == "3s" else "Do"
            yield Candidate(
                "questions_do",
                "mcq",
                "___ " + doc[1:].text,
                "Choose the right word to start the question.",
                f"The subject '{subj.text}' is {'he/she/it' if person == '3s' else 'not he/she/it'}"
                f", so the question starts with '{right}'.",
                f"Chủ ngữ '{subj.text}' "
                f"{'là' if person == '3s' else 'không phải'} ngôi thứ ba số ít"
                f" nên câu hỏi bắt đầu bằng '{right}'.",
                options=[right, "Do" if right == "Does" else "Does", "Is", "Are"],
                base_quality=0.88,
            )
            return
    for t in doc:
        if t.lower_ == "there" and t.dep_ == "expl" and t.head.lemma_ == "be":
            be = t.head
            if be.i != t.i + 1 or be.lower_ not in ("is", "are", "was", "were"):
                continue
            attr = next((c for c in be.children if c.dep_ == "attr"), None)
            if (
                attr is None
                or attr.tag_ not in ("NN", "NNS")
                or any(c.dep_ == "conj" for c in attr.children)
            ):
                continue
            plural = attr.tag_ == "NNS"
            if plural != (be.lower_ in ("are", "were")):
                continue
            if any(c.dep_ == "mark" and c.lower_ in ("if", "whether") for c in be.children):
                continue  # "I wonder if there were any way ...": the subjunctive fits too
            past = be.lower_ in ("was", "were")
            right = be.text
            # both distractors have the wrong number: "were" for "are" would fit too
            wrong = ["was", "is"] if plural else ["were", "are"]
            wrong += ["be", "has"]
            yield Candidate(
                "there_be",
                "mcq",
                _blanked(doc, be.i, be.i),
                "Choose the correct form of 'be'.",
                f"'{attr.text}' is {'plural' if plural else 'singular'}, "
                f"so we say 'there {right}'.",
                f"'{attr.text}' là danh từ {'số nhiều' if plural else 'số ít'} "
                f"nên dùng 'there {right}'.",
                options=[right, *[w for w in wrong if w.lower() != right.lower()]][:4],
                base_quality=0.88,
                tags=["past" if past else "present"],
            )
            return


_REFLEXIVE = {
    "1s": "myself",
    "3s_he": "himself",
    "3s_she": "herself",
    "3s_it": "itself",
    "we": "ourselves",
    "they": "themselves",
}
_SUBJECT_REFLEXIVE = {
    "i": "myself",
    "he": "himself",
    "she": "herself",
    "it": "itself",
    "we": "ourselves",
    "they": "themselves",
}


def reflexive_items(doc) -> Iterator[Candidate]:
    for t in doc:
        if t.lower_ not in _SUBJECT_REFLEXIVE.values() or t.dep_ not in ("dobj", "pobj"):
            continue
        verb = t.head if t.dep_ == "dobj" else t.head.head
        subj = next((c for c in verb.children if c.dep_ == "nsubj"), None)
        if subj is None or subj.lower_ not in _SUBJECT_REFLEXIVE:
            continue
        if _SUBJECT_REFLEXIVE[subj.lower_] != t.lower_:
            continue
        others = [
            r for r in ("myself", "himself", "herself", "themselves", "ourselves") if r != t.lower_
        ]
        yield Candidate(
            "reflexive_pronouns",
            "mcq",
            _blanked(doc, t.i, t.i),
            "Choose the correct reflexive pronoun.",
            f"The subject is '{subj.text}', so the reflexive pronoun is '{t.lower_}'.",
            f"Chủ ngữ là '{subj.text}' nên đại từ phản thân là '{t.lower_}'.",
            options=[t.lower_, *others[:3]],
            base_quality=0.9,
        )
        return


_POSSESSIVE_ADJ = {
    "my": "mine",
    "your": "yours",
    "his": "his",
    "her": "hers",
    "our": "ours",
    "their": "theirs",
}
_POSSESSIVE_WRONG = {
    "my": ("mine", "me", "I"),
    "your": ("yours", "you're", "you"),
    "her": ("hers", "she", "herself"),
    "our": ("ours", "us", "we"),
    "their": ("theirs", "they're", "them"),
}


def possessive_items(doc) -> Iterator[Candidate]:
    for t in doc:
        low = t.lower_
        if low in _POSSESSIVE_ADJ and t.dep_ == "poss" and low != "his":
            options = [low, *_POSSESSIVE_WRONG[low]]
            yield Candidate(
                "possessives",
                "mcq",
                _blanked(doc, t.i, t.i),
                "Choose the correct word.",
                f"Before a noun ('{t.head.text}') we use the possessive adjective '{low}'.",
                f"Trước danh từ ('{t.head.text}') dùng tính từ sở hữu '{low}'.",
                options=options,
                base_quality=0.88,
            )
            return
        if (
            low in _POSSESSIVE_ADJ.values()
            and low not in ("his", "her")
            and t.dep_ in ("attr", "dobj", "pobj", "nsubj")
            and t.tag_ == "PRP"
        ):
            adj = next(k for k, v in _POSSESSIVE_ADJ.items() if v == low)
            yield Candidate(
                "possessives",
                "mcq",
                _blanked(doc, t.i, t.i),
                "Choose the correct word.",
                f"Without a noun after it, we use the possessive pronoun '{low}'.",
                f"Khi không có danh từ theo sau, dùng đại từ sở hữu '{low}'.",
                options=[
                    low,
                    adj,
                    {"mine": "me", "yours": "you", "ours": "us", "theirs": "them"}[low],
                ],
                base_quality=0.86,
            )
            return


def adverb_items(doc) -> Iterator[Candidate]:
    for t in doc:
        if t.tag_ != "RB" or not t.lower_.endswith("ly") or t.dep_ != "advmod":
            continue
        if t.head.pos_ != "VERB" or len(t.text) < 6:
            continue
        adj = t.lower_[:-2]
        if adj.endswith("i"):
            adj = adj[:-1] + "y"
        from banana_english.contentbank.lexicon import zipf

        if zipf(adj) < 3.5 or adj in ("on", "ear", "on", "bare", "near", "hard", "late"):
            continue
        yield Candidate(
            "adjectives_adverbs",
            "mcq",
            _blanked(doc, t.i, t.i),
            "Adjective or adverb? Choose the correct word.",
            f"The word describes the verb '{t.head.text}', so we need the adverb '{t.lower_}', "
            f"not the adjective '{adj}'.",
            f"Từ này bổ nghĩa cho động từ '{t.head.text}' nên cần trạng từ '{t.lower_}', không "
            f"dùng tính từ '{adj}'.",
            options=[t.lower_, adj],
            base_quality=0.84,
        )
        return


def contrast_items(doc) -> Iterator[Candidate]:
    for t in doc:
        if t.lower_ == "although" and t.dep_ == "mark":
            clause = True  # options[0] is the right one: although / despite
        elif t.lower_ == "despite" and t.dep_ == "prep":
            clause = False
        else:
            continue
        # distractors that cannot fit grammatically: prepositions before a clause,
        # conjunctions before a noun phrase
        opts = (
            ["although", "despite", "in spite of", "because of"]
            if clause
            else ["despite", "although", "even though", "because"]
        )
        yield Candidate(
            "contrast_linkers",
            "mcq",
            _blanked(doc, t.i, t.i),
            "Choose the correct linking word.",
            (
                "'although' is followed by a clause (subject + verb) and shows contrast."
                if clause
                else "'despite' is followed by a noun or -ing form and shows contrast."
            ),
            (
                "'although' + mệnh đề (chủ ngữ + động từ), diễn tả sự tương phản."
                if clause
                else "'despite' + danh từ hoặc V-ing, diễn tả sự tương phản."
            ),
            options=opts,
            base_quality=0.84,
        )
        return


def ordering_items(doc) -> Iterator[Candidate]:
    """Short statements without movable adverbs or phrases: only one natural order."""
    words = [t for t in doc if not t.is_punct]
    if not (4 <= len(words) <= 7) or doc[-1].text != ".":
        return
    if any(
        t.pos_ in ("ADV", "INTJ", "CCONJ", "SCONJ") or t.dep_ in ("npadvmod", "prep") for t in words
    ):
        return
    if any(t.ent_type_ and t.i != 0 for t in words):
        return
    pieces: list[str] = []
    for t in words:  # keep contractions with their word: "It's", "don't"
        if t.text.startswith("'") or t.lower_ == "n't":
            if not pieces:
                return
            pieces[-1] += t.text
        else:
            pieces.append(t.text)
    if len(set(pieces)) != len(pieces) or len(pieces) < 4:
        return
    import random

    rng = random.Random(doc.text)
    shuffled = pieces[:]
    for _ in range(10):
        rng.shuffle(shuffled)
        if shuffled != pieces and shuffled[0] != pieces[0]:
            break
    else:
        return
    yield Candidate(
        "word_order",
        "ordering",
        "Put the words in the right order.",
        "Tap the words in the right order to make a sentence.",
        f"The order is subject + verb + the rest: {doc.text}",
        f"Trật tự câu: chủ ngữ + động từ + các thành phần còn lại: {doc.text}",
        options=shuffled,
        pieces=pieces,
        base_quality=0.72,
    )


def conditional_items(doc) -> Iterator[Candidate]:
    """First, second and third conditionals: the if-clause tense decides the main clause."""
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is None or root.pos_ != "VERB" or doc[-1].text == "?":
        return
    cond = next(
        (
            c
            for c in root.children
            if c.dep_ == "advcl" and any(m.lower_ == "if" and m.dep_ == "mark" for m in c.children)
        ),
        None,
    )
    if cond is None or any(c.dep_ == "neg" for c in root.children):
        return
    auxes = sorted((c for c in root.children if c.dep_ == "aux"), key=lambda t: t.i)
    if not auxes or auxes[-1].i > root.i:
        return
    main = [a.lower_ for a in auxes]
    lemma = root.lemma_.lower()
    if not re.fullmatch(r"[a-z]+", lemma) or lemma in TWO_PARTICIPLES:
        return
    cond_aux = [c.lower_ for c in cond.children if c.dep_ == "aux"]
    vbn, vbd, vbz = inflect(lemma, "VBN"), inflect(lemma, "VBD"), inflect(lemma, "VBZ")
    if main == ["will"] and root.tag_ == "VB" and cond.tag_ in ("VBZ", "VBP") and not cond_aux:
        kind, right = 1, f"will {root.text}"
        wrong = [f"would {lemma}", f"would have {vbn}", vbd]
    elif (
        main == ["would"]
        and root.tag_ == "VB"
        and (cond.tag_ == "VBD" and not cond_aux or cond.lower_ == "were")
    ):
        kind, right = 2, f"would {root.text}"
        wrong = [f"will {lemma}", f"would have {vbn}", vbz]
    elif main == ["would", "have"] and root.tag_ == "VBN" and cond_aux == ["had"]:
        kind, right = 3, f"would have {root.text}"
        wrong = [f"will {lemma}", vbz, f"will have {vbn}"]
    else:
        return
    start = auxes[0].i
    if any(t.pos_ not in ("AUX",) and t.i != root.i for t in doc[start : root.i + 1]):
        return
    why = {
        1: (
            "A real possibility: if + present simple, will + base form ({ans}).",
            "Điều kiện có thể xảy ra: if + hiện tại đơn, will + động từ nguyên mẫu ({ans}).",
        ),
        2: (
            "An unreal or unlikely present: if + past simple, would + base form ({ans}).",
            "Điều kiện không có thật ở hiện tại: if + quá khứ đơn, would + động từ nguyên mẫu "
            "({ans}).",
        ),
        3: (
            "An unreal past: if + past perfect, would have + past participle ({ans}).",
            "Điều kiện không có thật trong quá khứ: if + quá khứ hoàn thành, would have + quá "
            "khứ phân từ ({ans}).",
        ),
    }[kind]
    yield Candidate(
        "conditionals",
        "mcq",
        _blanked(doc, start, root.i, lemma),
        "Choose the correct form of the verb in brackets.",
        why[0].format(ans=right),
        why[1].format(ans=right),
        options=[right, *[w for w in wrong if w and w.lower() != right.lower()]],
        base_quality=0.85,
        tags=[f"type{kind}"],
    )


def quantifier_items(doc) -> Iterator[Candidate]:
    for t in doc:
        if t.lower_ not in ("much", "many") or t.dep_ != "amod" or t.i + 1 >= len(doc):
            continue
        noun = doc[t.i + 1]
        if t.head.i != noun.i:
            continue
        countable = noun.tag_ == "NNS"
        if (t.lower_ == "many") != countable or noun.tag_ not in ("NN", "NNS"):
            continue
        yield Candidate(
            "quantifiers",
            "mcq",
            _blanked(doc, t.i, t.i),
            "Choose much or many.",
            f"'{noun.text}' is "
            + (
                "a plural countable noun, so we use many."
                if countable
                else "uncountable, so we use much."
            ),
            f"'{noun.text}' là "
            + (
                "danh từ đếm được số nhiều nên dùng many."
                if countable
                else "danh từ không đếm được nên dùng much."
            ),
            options=[t.lower_, "much" if countable else "many", "a lot"],
            base_quality=0.86,
        )
        return


def error_items(doc) -> Iterator[Candidate]:
    """Find the mistake: one known error is put into the original sentence (wrong agreement or
    verb form), and the sentence is split into four parts, one of which holds the error."""
    g = _verb_group(doc)
    if g is None or g.lemma in TWO_PARTICIPLES:
        return
    right = doc[g.start : g.end + 1].text
    if tense_form(g.tense, g.lemma, g.person) != right:
        return
    wrong = _form_distractors(g, right)
    if not wrong:
        return
    bad = wrong[0]  # the agreement error: the clearest one
    if not (7 <= len(doc) <= 20):
        return
    # four parts: before the verb group, the (wrong) verb group, and the rest split in two
    before = doc[: g.start].text.strip()
    after_tokens = [t for t in doc[g.end + 1 :] if not (t.is_punct and t.i == len(doc) - 1)]
    if not before or len(after_tokens) < 3:
        return
    mid = len(after_tokens) // 2
    part3 = doc[after_tokens[0].i : after_tokens[mid - 1].i + 1].text
    part4 = doc[after_tokens[mid].i : after_tokens[-1].i + 1].text
    parts = [before, bad, part3, part4]
    if len(set(parts)) < 4 or any(not p for p in parts):
        return
    end = doc[-1].text if doc[-1].is_punct else ""
    sentence = " ".join(f"[{p}]" for p in parts) + end
    en_t, vi_t = TENSE_NAME[g.tense]
    yield Candidate(
        g.tense,
        "error_id",
        sentence,
        "One part of the sentence is wrong. Which one?",
        f"'{bad}' is wrong: with the subject '{g.subject.text}' the {en_t} is '{right}'.",
        f"'{bad}' sai: với chủ ngữ '{g.subject.text}', dạng {vi_t} đúng là '{right}'.",
        options=[bad, before, part3, part4],
        base_quality=0.8,
        tags=["error:" + g.tense],
    )


DETECTORS = (
    tense_items,
    article_items,
    preposition_items,
    comparison_items,
    gerund_infinitive_items,
    modal_items,
    passive_items,
    relative_items,
    agreement_items,
    reflexive_items,
    possessive_items,
    adverb_items,
    contrast_items,
    ordering_items,
    conditional_items,
    quantifier_items,
    error_items,
)


def candidates(doc) -> Iterator[Candidate]:
    for detector in DETECTORS:
        try:
            yield from detector(doc)
        except (IndexError, KeyError, AttributeError, TypeError):
            continue  # a parse we do not understand: skip the sentence for this detector


def item_level(doc, point: str) -> str:
    lemmas = [
        t.lemma_.lower() for t in doc if t.is_alpha and t.pos_ in ("NOUN", "VERB", "ADJ", "ADV")
    ]
    words = sum(1 for t in doc if not t.is_punct)
    vocab = level_of_words(lemmas)
    level = max_level(POINT_LEVEL[point], vocab, length_level(words))
    return level


def difficulty_of(words: int, qtype: str) -> str:
    """Difficulty inside a level: longer sentences and productive or error-spotting tasks are
    harder than picking a form in a short sentence."""
    score = (words > 10) + (words > 16) + (qtype in ("fill_blank", "error_id", "ordering"))
    return ("easy", "medium", "hard", "hard")[score]


def topic_for(doc) -> str:
    return topic_of([t.lemma_.lower() for t in doc if t.is_alpha])
