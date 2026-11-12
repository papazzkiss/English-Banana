"""Word levels, topics and the content filter used by every generator.

CEFR level of a word: the CEFR-J Wordlist (A1-B2); words it does not list are levelled by
frequency (wordfreq Zipf scale): common -> B1, less common -> B2, rare -> C1.
"""

from __future__ import annotations

import csv
import re
from functools import cache

from banana_english.config.settings import PROJECT_ROOT

LEVELS = ("A1", "A2", "B1", "B2", "C1")
RANK = {lvl: i for i, lvl in enumerate(LEVELS)}
CEFRJ = PROJECT_ROOT / "content/vocabulary/sources/cefrj-vocabulary-profile-1.5.csv"

_POS_MAP = {
    "noun": "NOUN",
    "verb": "VERB",
    "adjective": "ADJ",
    "adverb": "ADV",
}


@cache
def cefrj() -> dict[str, str]:
    """lemma -> lowest CEFR level of any of its entries (all parts of speech)."""
    levels: dict[str, str] = {}
    with CEFRJ.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for word in row["headword"].split("/"):
                w = word.strip().lower()
                if w and (w not in levels or RANK[row["CEFR"]] < RANK[levels[w]]):
                    levels[w] = row["CEFR"]
    return levels


@cache
def cefrj_pos() -> dict[tuple[str, str], str]:
    """(lemma, spaCy POS) -> CEFR level."""
    out: dict[tuple[str, str], str] = {}
    with CEFRJ.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pos = _POS_MAP.get(row["pos"])
            if not pos:
                continue
            for word in row["headword"].split("/"):
                key = (word.strip().lower(), pos)
                if key not in out or RANK[row["CEFR"]] < RANK[out[key]]:
                    out[key] = row["CEFR"]
    return out


_SPACY_POS = {"noun": "NOUN", "verb": "VERB", "adjective": "ADJ", "adverb": "ADV"}


def learner_word(lemma: str, pos: str, max_level: str = "B1") -> bool:
    """A word a learner knows by this level with this part of speech (CEFR-J): the only kind
    of word offered as a synonym (not "legion" for "numerous")."""
    level = cefrj_pos().get((lemma, _SPACY_POS.get(pos, pos)))
    return level is not None and RANK[level] <= RANK[max_level]


def zipf(word: str) -> float:
    from wordfreq import zipf_frequency

    return zipf_frequency(word, "en")


@cache
def word_level(lemma: str) -> str:
    lemma = lemma.lower()
    level = cefrj().get(lemma)
    if level:
        return level
    z = zipf(lemma)
    if z >= 4.5:
        return "B1"
    if z >= 3.3:
        return "B2"
    return "C1"


def length_level(n_words: int) -> str:
    if n_words <= 7:
        return "A1"
    if n_words <= 11:
        return "A2"
    if n_words <= 17:
        return "B1"
    if n_words <= 25:
        return "B2"
    return "C1"


def max_level(*levels: str) -> str:
    return max(levels, key=RANK.__getitem__)


def level_of_words(lemmas: list[str]) -> str:
    """The level of the hardest word, ignoring a single outlier in longer sentences."""
    ranks = sorted((RANK[word_level(w)] for w in lemmas), reverse=True)
    if not ranks:
        return "A1"
    if len(ranks) >= 8 and ranks[0] - ranks[1] >= 2:  # one rare word does not make C1
        return LEVELS[ranks[1] + 1]
    return LEVELS[ranks[0]]


# --- topics ---------------------------------------------------------------------------------

TOPICS: dict[str, tuple[str, ...]] = {
    "food": (
        "eat",
        "food",
        "cook",
        "restaurant",
        "breakfast",
        "lunch",
        "dinner",
        "meal",
        "apple",
        "bread",
        "rice",
        "coffee",
        "tea",
        "fruit",
        "vegetable",
        "meat",
        "fish",
        "cake",
        "hungry",
        "delicious",
        "kitchen",
        "menu",
        "pizza",
        "soup",
        "egg",
        "milk",
        "sugar",
    ),
    "travel": (
        "travel",
        "trip",
        "airport",
        "train",
        "hotel",
        "ticket",
        "flight",
        "station",
        "passport",
        "tourist",
        "journey",
        "holiday",
        "vacation",
        "abroad",
        "plane",
        "bus",
        "luggage",
        "map",
        "visit",
        "beach",
        "country",
        "city",
        "museum",
    ),
    "work": (
        "work",
        "job",
        "office",
        "boss",
        "meeting",
        "company",
        "colleague",
        "salary",
        "employee",
        "manager",
        "career",
        "interview",
        "business",
        "customer",
        "project",
        "contract",
        "report",
        "deadline",
    ),
    "education": (
        "school",
        "teacher",
        "student",
        "class",
        "exam",
        "study",
        "homework",
        "university",
        "lesson",
        "learn",
        "college",
        "course",
        "library",
        "test",
        "grade",
        "science",
        "history",
        "math",
        "english",
        "language",
    ),
    "family": (
        "mother",
        "father",
        "sister",
        "brother",
        "family",
        "parent",
        "child",
        "wife",
        "husband",
        "son",
        "daughter",
        "grandmother",
        "grandfather",
        "baby",
        "uncle",
        "aunt",
        "cousin",
        "marry",
        "wedding",
    ),
    "health": (
        "doctor",
        "hospital",
        "sick",
        "ill",
        "medicine",
        "headache",
        "health",
        "pain",
        "fever",
        "cold",
        "nurse",
        "exercise",
        "diet",
        "sleep",
        "tired",
        "healthy",
        "disease",
        "patient",
    ),
    "shopping": (
        "buy",
        "shop",
        "store",
        "price",
        "cheap",
        "expensive",
        "sell",
        "market",
        "pay",
        "money",
        "dollar",
        "cost",
        "discount",
        "clothes",
        "shoe",
        "dress",
    ),
    "technology": (
        "computer",
        "phone",
        "internet",
        "email",
        "software",
        "app",
        "robot",
        "technology",
        "website",
        "online",
        "digital",
        "program",
        "data",
        "machine",
        "camera",
        "battery",
        "screen",
        "keyboard",
        "artificial",
        "intelligence",
    ),
    "nature": (
        "weather",
        "rain",
        "snow",
        "sun",
        "wind",
        "tree",
        "river",
        "mountain",
        "animal",
        "dog",
        "cat",
        "bird",
        "forest",
        "sea",
        "flower",
        "garden",
        "sky",
        "lake",
        "island",
        "plant",
        "horse",
    ),
    "environment": (
        "pollution",
        "climate",
        "environment",
        "recycle",
        "energy",
        "planet",
        "waste",
        "carbon",
        "global",
        "warming",
        "nature",
        "species",
        "protect",
    ),
    "sports": (
        "football",
        "soccer",
        "tennis",
        "team",
        "match",
        "swim",
        "run",
        "sport",
        "player",
        "win",
        "lose",
        "game",
        "ball",
        "race",
        "coach",
        "olympic",
        "basketball",
    ),
    "entertainment": (
        "movie",
        "film",
        "music",
        "song",
        "tv",
        "television",
        "concert",
        "book",
        "novel",
        "play",
        "actor",
        "singer",
        "party",
        "dance",
        "guitar",
        "piano",
        "art",
        "painting",
        "show",
    ),
    "home": (
        "house",
        "room",
        "door",
        "window",
        "bed",
        "home",
        "apartment",
        "flat",
        "table",
        "chair",
        "sofa",
        "garden",
        "neighbor",
        "neighbour",
        "clean",
        "wash",
    ),
    "business": (
        "bank",
        "economy",
        "market",
        "company",
        "profit",
        "price",
        "trade",
        "invest",
        "finance",
        "tax",
        "industry",
        "product",
        "sales",
    ),
    "science": (
        "science",
        "scientist",
        "research",
        "experiment",
        "chemical",
        "physics",
        "biology",
        "energy",
        "atom",
        "cell",
        "theory",
        "space",
        "earth",
        "moon",
        "star",
    ),
    "society": (
        "government",
        "law",
        "city",
        "people",
        "population",
        "culture",
        "history",
        "war",
        "king",
        "queen",
        "president",
        "election",
        "religion",
        "tradition",
    ),
    "communication": (
        "call",
        "letter",
        "message",
        "phone",
        "talk",
        "speak",
        "write",
        "email",
        "news",
        "newspaper",
        "language",
        "conversation",
    ),
}
_TOPIC_WORDS = {w: t for t, words in TOPICS.items() for w in words}


# words that name a topic in a short learner text but mostly mean something else in an
# encyclopedia article ("the upper house", "a TV show", "a game of politics", "a cell")
AMBIGUOUS_TOPIC_WORDS = frozenset(
    [
        "house",
        "show",
        "play",
        "game",
        "run",
        "cell",
        "star",
        "space",
        "plant",
        "test",
        "class",
        "program",
        "report",
        "project",
        "book",
        "clean",
        "cold",
        "market",
        "country",
        "city",
        "visit",
        "history",
        "language",
        "table",
        "win",
        "lose",
        "party",
    ]
)


def topic_of(
    lemmas: list[str],
    default: str = "daily_life",
    min_hits: int = 1,
    margin: float = 1.0,
    skip: frozenset[str] = frozenset(),
) -> str:
    """The topic with the most keyword hits; `default` unless it has `min_hits` and leads the
    runner-up by `margin` times."""
    counts: dict[str, int] = {}
    for w in lemmas:
        t = _TOPIC_WORDS.get(w.lower())
        if t and w.lower() not in skip:
            counts[t] = counts.get(t, 0) + 1
    if not counts or max(counts.values()) < min_hits:
        return default
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], list(TOPICS).index(kv[0])))
    if len(ranked) > 1 and ranked[0][1] < margin * ranked[1][1]:
        return default
    return ranked[0][0]


# --- content filter ---------------------------------------------------------------------------

_BLOCK = re.compile(
    r"\b(sex\w*|porn\w*|rap(e|ed|ist|ing)|nud(e|ity)|naked|penis|vagina|breasts?|orgasm\w*|"
    r"kill(s|ed|er|ing)?|murder\w*|suicid\w*|shoot(s|ing)?|shot\s+(him|her|them|dead)|gun\w*|"
    r"bomb\w*|terror\w*|corpse|blood(y|ied)?|stab\w*|tortur\w*|slave\w*|nazi\w*|hitler|"
    r"drug(s|ged)?|cocaine|heroin|marijuana|weed|drunk|hangover|cigarettes?|smok(e|es|ed|ing)|"
    r"fuck\w*|shit\w*|bitch\w*|bastard\w*|damn\w*|crap|piss\w*|asshole|dick|whore|slut|"
    r"idiot|stupid|moron|ugly|fat\s+(girl|woman|man|boy)|hate\s+you|die|dies|dying|dead|death)\b",
    re.I,
)


def is_clean(text: str) -> bool:
    """False for violence, sex, drugs, profanity, insults and death: the bank is for
    learners of every age."""
    return _BLOCK.search(text) is None
