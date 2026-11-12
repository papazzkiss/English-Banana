"""The single scoring rubric shared by EVERY assessment (grammar, listening, speaking,
conversation, vocabulary ratings), so that 70 in grammar means the same as 70 in listening.

Every LLM prompt renders its rubric from RUBRIC_BANDS; never hand-write a second scale.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RubricBand:
    minimum: int
    label: str
    description: str


RUBRIC_BANDS: tuple[RubricBand, ...] = (
    RubricBand(90, "excellent", "correct and natural; fully answers the task"),
    RubricBand(70, "good", "correct, but awkward phrasing or a trivial slip"),
    RubricBand(40, "minor_error", "minor error, e.g. wrong article or wrong preposition"),
    RubricBand(0, "major_error", "major error (wrong tense, wrong verb form) or off-task"),
)

CORRECT_THRESHOLD = 70  # is_correct <=> score >= 70


def band_for(score: float) -> RubricBand:
    for band in RUBRIC_BANDS:
        if score >= band.minimum:
            return band
    return RUBRIC_BANDS[-1]


def render_rubric() -> str:
    lines = []
    upper = 100
    for band in RUBRIC_BANDS:
        lines.append(f"- {band.minimum}-{upper}: {band.description}")
        upper = band.minimum - 1
    return "\n".join(lines)


# --- deterministic scoring from categorical LLM judgements (prompt v4+) --------------------
# Calibration showed the LLM names errors reliably but picks inconsistent NUMBERS (v2: +20
# bias; v3: listed errors yet scored 95). So the LLM only judges categories and this function
# turns them into a score inside the matching rubric band.

GRAMMAR_SCORES = {
    "excellent": 95,
    "good": 80,
    "one_minor": 55,
    "minor": 45,
    "one_major": 25,
    "major": 15,
}


def score_from_findings(severities: list[str], natural: bool) -> int:
    majors = sum(1 for s in severities if s == "major")
    minors = sum(1 for s in severities if s == "minor")
    if majors:
        return GRAMMAR_SCORES["one_major"] if majors == 1 else GRAMMAR_SCORES["major"]
    if minors:
        return GRAMMAR_SCORES["one_minor"] if minors == 1 else GRAMMAR_SCORES["minor"]
    return GRAMMAR_SCORES["excellent"] if natural else GRAMMAR_SCORES["good"]


COMPREHENSION_SCORES = {"fully": 95, "partly": 55, "not": 15}

# Severity is a property of the error TYPE, not a model judgement (calibration v4: the model
# labelled every error "major"). Minor = 40-69 band, major = 0-39 band.
MINOR_TAGS = frozenset(
    {"article", "preposition", "spelling", "word_choice", "comparative_form", "other"}
)


def severity_for(tag: str) -> str:
    return "minor" if tag in MINOR_TAGS else "major"
