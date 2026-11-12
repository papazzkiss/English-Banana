"""Bilingual (English–Vietnamese) tutoring policy for AI Monkey.

English is what the learner practises; Vietnamese is a support language for explanations and
corrections. This module decides, for one reply, which language to chat, explain and correct
in, how much to correct, and what the learner wants now. It is plain code (no LLM call), so the
decision is fast, testable and cannot be talked out of the system prompt.

* LanguagePreferences — what persists across turns (the client keeps it, like the history).
* TEACHING_MODES      — named presets of the three languages.
* parse_message       — natural commands in Vietnamese or English ("từ giờ chỉ nói tiếng Anh",
                        "if I make a mistake, explain it in Vietnamese", "đừng sửa lỗi nữa").
                        Commands about the future persist; "explain this in Vietnamese" only
                        changes the current reply.
* TurnPolicy          — the resolved choices for one reply, rendered as a short app note.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field, fields, replace
from typing import Literal

Language = Literal["auto", "en", "vi"]
Corrections = Literal["auto", "off", "strict"]
TeachingMode = Literal[
    "auto", "immersion", "vietnamese_support", "bilingual", "free_chat", "custom"
]
Intent = Literal["chat", "explain", "translate", "example", "check"]
Detected = Literal["en", "vi", "mixed"]

LANGUAGE_NAME = {"en": "English", "vi": "Vietnamese", "auto": "Auto"}
MODE_NAME = {
    "auto": "Auto",
    "immersion": "English Immersion",
    "vietnamese_support": "Vietnamese Support",
    "bilingual": "Bilingual",
    "free_chat": "Free Chat",
    "custom": "Custom",
}
CORRECTIONS_NAME = {"auto": "Auto", "off": "Off", "strict": "All mistakes"}

# conversation, correction, explanation
TEACHING_MODES: dict[str, tuple[Language, Language, Language]] = {
    "auto": ("auto", "auto", "auto"),
    "immersion": ("en", "en", "en"),
    "vietnamese_support": ("en", "vi", "vi"),
    "bilingual": ("en", "en", "vi"),
    "free_chat": ("auto", "auto", "auto"),  # like auto, but the chat follows the learner too
}


@dataclass(frozen=True)
class LanguagePreferences:
    mode: TeachingMode = "auto"
    conversation_language: Language = "auto"
    explanation_language: Language = "auto"
    correction_language: Language = "auto"
    corrections: Corrections = "auto"

    def with_mode(self, mode: TeachingMode) -> LanguagePreferences:
        if mode not in TEACHING_MODES:
            return replace(self, mode=mode)
        conversation, correction, explanation = TEACHING_MODES[mode]
        return replace(
            self,
            mode=mode,
            conversation_language=conversation,
            correction_language=correction,
            explanation_language=explanation,
        )

    def normalized(self) -> LanguagePreferences:
        """The mode that matches the three languages (free_chat stays free_chat)."""
        languages = (
            self.conversation_language,
            self.correction_language,
            self.explanation_language,
        )
        if self.mode in TEACHING_MODES and TEACHING_MODES[self.mode] == languages:
            return self
        for mode, preset in TEACHING_MODES.items():
            if preset == languages:
                return replace(self, mode=mode)  # type: ignore[arg-type]
        return replace(self, mode="custom")


def describe_changes(before: LanguagePreferences, after: LanguagePreferences) -> list[str]:
    """Human-readable settings changes, e.g. ["Chat: English", "Corrections: Off"]."""
    labels = {
        "mode": ("Mode", MODE_NAME),
        "conversation_language": ("Chat", LANGUAGE_NAME),
        "explanation_language": ("Explanations", LANGUAGE_NAME),
        "correction_language": ("Corrections in", LANGUAGE_NAME),
        "corrections": ("Corrections", CORRECTIONS_NAME),
    }
    changes = []
    for f in fields(LanguagePreferences):
        old, new = getattr(before, f.name), getattr(after, f.name)
        if old != new:
            label, names = labels[f.name]
            changes.append(f"{label}: {names[new]}")
    return changes


# --- language detection ------------------------------------------------------------------------

# Letters only Vietnamese uses (ă â đ ê ô ơ ư, tone marks: U+1EA0-U+1EF9) plus the Latin-1 toned
# vowels; one of these in a word marks it as Vietnamese.
_VI_LETTER = re.compile(r"[ăâđêôơưĩũẠ-ỹàáãèéìíòóõùúýỳ]", re.I)
# Common Vietnamese words typed without accents that are not English words.
_VI_PLAIN = frozenset(
    {
        "toi",
        "khong",
        "cua",
        "nhe",
        "nha",
        "voi",
        "minh",
        "duoc",
        "bang",
        "tieng",
        "giai",
        "thich",
        "dich",
        "chuyen",
        "roi",
        "vay",
        "nhu",
        "nao",
        "giup",
        "gium",
        "sao",
        "dung",
        "khi",
        "thi",
        "cau",
        "nay",
        "la",
        "gi",
        "lam",
        "sua",
        "loi",
        "nua",
    }
)
_WORD = re.compile(r"[^\W\d_]+")


def detect_language(text: str) -> Detected:
    """en, vi or mixed. A few Vietnamese words (a name like "Hà Nội") keep a sentence English."""
    words = _WORD.findall(text.lower())
    if not words:
        return "en"
    vi = sum(1 for w in words if _VI_LETTER.search(w) or w in _VI_PLAIN)
    ratio = vi / len(words)
    if vi == 0 or (vi < 3 and ratio < 0.5):
        return "en"
    return "vi" if ratio >= 0.6 else "mixed"


# --- Vietnamese grammar terms ------------------------------------------------------------------

# Vietnamese names of English grammar topics -> the topic, with an anchor example. The model
# explains English grammar well when asked in English but confuses the Vietnamese names (live
# run: "thì hiện tại đơn giản" explained as "happening now"); naming the topic fixes that.
GRAMMAR_TERMS: tuple[tuple[str, str], ...] = (
    ("hien tai don", "the present simple (I eat, she eats: habits, routines, facts)"),
    ("hien tai tiep dien", "the present continuous (I am eating: happening now)"),
    ("hien tai hoan thanh", "the present perfect (I have eaten: from the past up to now)"),
    ("qua khu don", "the past simple (I ate: a finished time, e.g. yesterday)"),
    ("qua khu tiep dien", "the past continuous (I was eating)"),
    ("tuong lai don", "the future simple (I will eat)"),
    ("tuong lai gan", "be going to (I am going to eat: plans)"),
    ("cau dieu kien", "conditionals (if-sentences: zero, first, second, third)"),
    ("bi dong", "the passive voice (The cake was eaten)"),
    ("mao tu", "articles (a, an, the)"),
    ("gioi tu", "prepositions (in, on, at, ...)"),
    ("so sanh hon", "comparatives (bigger, more interesting)"),
    ("so sanh nhat", "superlatives (the biggest, the most interesting)"),
    ("danh dong tu", "gerunds (verb-ing as a noun: I like swimming)"),
    ("dong tu khuyet thieu", "modal verbs (can, must, should)"),
    ("tuong thuat", "reported speech (She said that she was tired)"),
    ("menh de quan he", "relative clauses (who, which, that)"),
)


def _plain(text: str) -> str:
    """Lowercase without Vietnamese accents, so typed-without-accents text matches too."""
    decomposed = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def grammar_topics(text: str) -> tuple[str, ...]:
    plain = _plain(text)
    return tuple(topic for term, topic in GRAMMAR_TERMS if term in plain)


# --- commands ------------------------------------------------------------------------------------


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I)


_EN_LANG = _rx(r"tiếng anh|tieng anh|\benglish\b")
_VI_LANG = _rx(r"tiếng việt|tieng viet|\bvietnamese\b|tiếng mẹ đẻ")
_PERSIST = _rx(
    r"từ (giờ|bây giờ|nay|lúc này)|\btu (gio|bay gio|nay)\b|về sau|luôn luôn|lúc nào cũng|"
    r"\bluôn\b|from now on|\balways\b|going forward|for the rest"
)
_ONLY = _rx(r"\bchỉ\b|\bonly\b|\bjust\b")
_TALK = _rx(
    r"nói chuyện|trò chuyện|giao tiếp|trả lời|\bnói\b|\bdùng\b|sử dụng|luyện|"
    r"noi chuyen|tro chuyen|tra loi|\bnoi\b|luyen|"
    r"\btalk|\bspeak|\bchat\b|practi[cs]e|\breply|\brespond|\banswer|\buse\b|\bconversation"
)
_EXPLAIN = _rx(r"giải thích|giai thich|hướng dẫn|\bexplain|\bexplanation")
_CORRECT = _rx(r"\bsửa\b|\bchữa\b|\bsua\b|\bcorrect|\bfix\b")
_MISTAKE = _rx(
    r"(nếu|khi|lúc|\bneu\b|\bkhi\b|\bif\b|\bwhen(ever)?\b)[^.?!]{0,25}"
    r"(sai|nhầm|lỗi|\bloi\b|mistake|error|wrong)"
)
_NO_CORRECT = _rx(
    r"(đừng|không cần|khỏi|thôi|\bdung\b|khong can|\bstop\b|\bdon'?t\b|\bdo not\b|no need to|"
    r"\bno more\b)[^.?!]{0,15}(sửa|chữa|\bsua\b|\bchua\b|correct)|"
    r"(không|khong)[^.?!]{0,10}(sửa|sua)[^.?!]{0,20}(nữa|nua)"
)
_STRICT = _rx(
    r"(sửa|chữa|\bsua\b|\bchua\b|correct)\w*[^.?!]{0,25}"
    r"(tất cả|\bhết\b|\bmọi\b|\bmỗi\b|tat ca|\ball\b|\bevery|\beach\b)|nghiêm khắc|\bstrict"
)
_RESUME = _rx(
    r"(sửa|chữa|\bsua\b|correct)\w*[^.?!]{0,15}(\blại\b|\blai\b|\bagain\b)|"
    r"(tiếp tục|tiep tuc|\bresume\b|bắt đầu)[^.?!]{0,10}(sửa|chữa|\bsua\b|correct)"
)
_AUTO = _rx(
    r"(chế độ|che do|\bmode\b|trở lại|quay lại|quay về|\bback to\b|\breset\b)[^.?!]{0,15}"
    r"(tự động|tu dong|\bauto\b)|^\W*(auto|tự động)\W*$"
)
_FREE = _rx(r"free chat|(chế độ|nói chuyện|trò chuyện|chat)[^.?!]{0,10}(tự do|tu do)")
_BILINGUAL = _rx(r"song ngữ|song ngu|\bbilingual\b")
_IMMERSION = _rx(r"\bimmersion\b")
_TRANSLATE = _rx(
    r"\bdịch\b|\bdich\b|translat|(nói|noi)[^.?!]{0,30}(thế nào|the nao)|"
    r"how (do|can|would) (you|i) say|nghĩa là|nghia la|\bmeans?\b"
)
_CHECK = _rx(
    r"\b(is|was|does) (this|it|that|my \w+)( sentence)? (correct|right|ok|okay|wrong|natural|"
    r"sound)|đúng không|dung khong|có đúng|co dung|sai ở đâu|sai o dau|sai chỗ nào|"
    r"\bcheck (my|this)|kiểm tra|kiem tra"
)
_WHY = _rx(r"tại sao|tai sao|vì sao|vi sao|sao lại|\bwhy\b|what does|nghĩa là gì")
# a question about how the language works: "thì hiện tại hoàn thành dùng khi nào?",
# "cách dùng since và for", "when do I use the past perfect?", "what's the difference between..."
# (not "bạn tên là gì?": that is small talk)
_ASK_USAGE = _rx(
    r"(dùng|sử dụng|\bdung\b|su dung)[^.?!]{0,20}(khi nào|khi nao|thế nào|the nao|ra sao|lúc nào)|"
    r"khi nào (thì )?(dùng|dung)|cách dùng|cach dung|cách sử dụng|"
    r"khác (nhau|gì|biệt)|khac (nhau|gi|biet)|thế nào là|the nao la|"
    r"(cấu trúc|công thức|cau truc|cong thuc)\b|"
    r"\b(thì|từ|cụm|câu|thi|tu)\b[^.?!]{0,40}\b(là gì|la gi|nghĩa gì)|"
    r"\bwhen (do|should|can|would) (i|we|you) use\b|\bhow (do|should|can) (i|we|you) use\b|"
    r"\bdifference between\b|\bwhat'?s the difference\b|\bwhat is the difference\b"
)
_EXAMPLE = _rx(r"ví dụ|vi du|\bexamples?\b")
_EN_DIRECTIVE = _rx(
    r"\b(you|me|let'?s|let us|please|monkey|i want|i'd like|if i|when i|whenever i)\b|"
    r"^\W*(explain|speak|talk|reply|answer|correct|translate|use|stop|don'?t|do not|keep|"
    r"switch|only|english|vietnamese)\b"
)
_CLAUSE_SPLIT = re.compile(r"[.!?;\n]+")


@dataclass(frozen=True)
class ParsedMessage:
    """What one learner message asks for."""

    preferences: LanguagePreferences  # after its lasting commands
    turn_explanation_language: Language | None = None  # "explain this in Vietnamese" (now only)
    intent: Intent = "chat"
    changes: tuple[str, ...] = field(default_factory=tuple)


def _is_directive(clause: str) -> bool:
    # Vietnamese in this chat is almost always addressed to the tutor; English needs a cue
    # ("my teacher always explains in Vietnamese" is not a command).
    return detect_language(clause) != "en" or bool(_EN_DIRECTIVE.search(clause))


def _intent(text: str) -> Intent:
    if _CHECK.search(text):
        return "check"
    if _TRANSLATE.search(text):
        return "translate"
    if _EXPLAIN.search(text) or _WHY.search(text) or _ASK_USAGE.search(text):
        return "explain"
    if _EXAMPLE.search(text):
        return "example"
    return "chat"


def parse_message(text: str, preferences: LanguagePreferences) -> ParsedMessage:
    prefs = preferences
    turn_explanation: Language | None = None
    requests: list[str] = []  # clauses that change no setting: what the learner wants now
    for clause in (c.strip() for c in _CLAUSE_SPLIT.split(text)):
        if not clause:
            continue
        before = prefs
        prefs, clause_turn = _apply_clause(clause, prefs)
        turn_explanation = clause_turn or turn_explanation
        if prefs == before:  # "explain this in Vietnamese" is still a request to explain
            requests.append(clause)
    prefs = prefs.normalized() if prefs != preferences else prefs
    return ParsedMessage(
        preferences=prefs,
        turn_explanation_language=turn_explanation,
        # a pure settings command ("if I'm wrong, explain it in Vietnamese") is not a request
        # to explain something now
        intent=_intent(". ".join(requests)),
        changes=tuple(describe_changes(preferences, prefs)),
    )


def _apply_clause(
    clause: str, prefs: LanguagePreferences
) -> tuple[LanguagePreferences, Language | None]:
    """One clause's commands: (lasting preferences, language for this reply only)."""
    if not _is_directive(clause) or _TRANSLATE.search(clause):
        return prefs, None
    if _AUTO.search(clause):
        return LanguagePreferences(), None
    if _FREE.search(clause):
        prefs = prefs.with_mode("free_chat")
    elif _BILINGUAL.search(clause):
        prefs = prefs.with_mode("bilingual")
    elif _IMMERSION.search(clause):
        prefs = prefs.with_mode("immersion")

    no_correct, strict = bool(_NO_CORRECT.search(clause)), bool(_STRICT.search(clause))
    if no_correct and not strict:
        prefs = replace(prefs, corrections="off")
    elif strict and not no_correct:
        prefs = replace(prefs, corrections="strict")
    elif _RESUME.search(clause) or (no_correct and strict):
        prefs = replace(prefs, corrections="auto")

    persist = bool(_PERSIST.search(clause))
    only = bool(_ONLY.search(clause))
    turn: Language | None = None
    # Each language mentioned applies to what the words just before it talk about:
    # "nói chuyện bằng tiếng Anh nhưng nếu tôi sai thì giải thích bằng tiếng Việt".
    mentions = sorted(
        [(m.start(), m.end(), "en") for m in _EN_LANG.finditer(clause)]
        + [(m.start(), m.end(), "vi") for m in _VI_LANG.finditer(clause)]
    )
    previous_end = 0
    for start, end, language in mentions:
        scope = clause[previous_end:start]
        previous_end = end
        lang: Language = language  # type: ignore[assignment]
        if _MISTAKE.search(scope):
            prefs = replace(prefs, correction_language=lang, explanation_language=lang)
        elif _CORRECT.search(scope):
            if persist:
                prefs = replace(prefs, correction_language=lang)
            else:
                turn = lang
        elif _EXPLAIN.search(scope):
            if persist:
                prefs = replace(prefs, explanation_language=lang, correction_language=lang)
            else:
                turn = lang
        elif only:  # "từ giờ chỉ nói tiếng Anh", "English only"
            prefs = replace(
                prefs,
                conversation_language=lang,
                explanation_language=lang,
                correction_language=lang,
            )
        elif _TALK.search(scope):
            prefs = replace(prefs, conversation_language=lang)
    return prefs, turn


def replay_preferences(learner_messages: Iterable[str]) -> LanguagePreferences:
    """Preferences implied by earlier commands, for clients that do not keep them."""
    prefs = LanguagePreferences()
    for text in learner_messages:
        prefs = parse_message(text, prefs).preferences
    return prefs


# --- the policy for one reply ---------------------------------------------------------------

_INTENT_TASK = {  # after "reply in <explanation language>: "
    "explain": "explain it in 2-4 short sentences with one full English example sentence in quotes",
    "translate": "give the English first, then a short note if useful",
    "example": "give one or two full English example sentences in quotes, briefly explained",
    "check": 'say if it is correct; if not, give "wrong" -> "right" and why',
}


_CORRECTION_LEVEL: dict[str, Literal["off", "gentle", "strict"]] = {
    "auto": "gentle",
    "off": "off",
    "strict": "strict",
}


@dataclass(frozen=True)
class TurnPolicy:
    learner_language: Detected
    conversation_language: Literal["en", "vi"]
    explanation_language: Literal["en", "vi"]
    correction_language: Literal["en", "vi"]
    corrections: Literal["off", "gentle", "strict"]
    intent: Intent
    changes: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()  # English grammar topics named in Vietnamese

    @property
    def is_default(self) -> bool:
        """An English chat turn with gentle English tips and no command: the system prompt's
        defaults, so no note at all (measured on Q6_K: even a one-line note changed the tips)."""
        return (
            self.intent == "chat"
            and self.conversation_language == "en"
            and self.correction_language == "en"
            and self.corrections == "gentle"
            and not self.changes
            and not self.topics
        )

    @property
    def detailed(self) -> bool:
        """The reply is an explanation, not a chat turn: it may be longer."""
        return self.intent != "chat" or self.corrections == "strict"

    def instruction(self) -> str:
        """The per-reply settings as ONE compact line appended to the learner's latest message
        ("" for a default English chat turn, whose rules are the system prompt's). Measured on
        Q6_K CPU, every prompt token costs ~35 ms uncached, so this stays a few dozen tokens."""
        if self.is_default:
            return ""
        chat = LANGUAGE_NAME[self.conversation_language]
        explain = LANGUAGE_NAME[self.explanation_language]
        correct = LANGUAGE_NAME[self.correction_language]
        tips = {
            "off": "none (do not correct them)",
            "strict": f'every mistake, as "wrong" -> "right" with a short reason in {correct}',
            "gentle": f"if they made a clear mistake, add one tip in {correct}"
            + (' like (Tip: nói "I went", không nói "I go".)' if correct == "Vietnamese" else ""),
        }[self.corrections]
        # one language instruction only: the chat language, or the task's (explain, check...)
        if self.intent == "chat":
            parts = [f"reply in {chat}", f"tips: {tips}"]
        else:
            parts = [f"reply in {explain}: {_INTENT_TASK[self.intent]}", f"tips: {tips}"]
        if self.topics:
            parts.append(f"topic: {'; '.join(self.topics)}")
        if self.changes:  # a settings command: confirm it, no tip (it primed invented ones)
            parts = [p for p in parts if not p.startswith("tips:")]
            parts.append(f"settings just changed: confirm in one short {explain} sentence")
        return "[App settings: " + "; ".join(parts) + "]"


def resolve(parsed: ParsedMessage, learner_text: str) -> TurnPolicy:
    detected = detect_language(learner_text)
    prefs = parsed.preferences
    if prefs.conversation_language != "auto":
        conversation = prefs.conversation_language
    else:  # an English tutor chats in English; Free Chat follows the learner
        conversation = "vi" if prefs.mode == "free_chat" and detected == "vi" else "en"
    explanation = (
        parsed.turn_explanation_language
        or (prefs.explanation_language if prefs.explanation_language != "auto" else None)
        or ("en" if detected == "en" else "vi")
    )
    correction = (
        parsed.turn_explanation_language
        or (prefs.correction_language if prefs.correction_language != "auto" else None)
        or explanation
    )
    return TurnPolicy(
        learner_language=detected,
        conversation_language=conversation,  # type: ignore[arg-type]
        explanation_language=explanation,  # type: ignore[arg-type]
        correction_language=correction,  # type: ignore[arg-type]
        corrections=_CORRECTION_LEVEL[prefs.corrections],
        intent=parsed.intent,
        changes=parsed.changes,
        topics=grammar_topics(learner_text),
    )
