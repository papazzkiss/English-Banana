"""Vocabulary review scoring (Phase 2) — deterministic, no LLM.

The learner optionally types the word, then presses Again / Hard / Good / Easy (SM-2 quality
1/3/4/5, as in Anki). A typed answer caps the rating so self-rating cannot hide a mistake:
* exact match (headword or spelling variant)  -> rating as pressed
* one typo away (two for 8+ letters)          -> at most Hard, "spelling" mistake
* wrong or empty typed answer                 -> Again
Score on the unified rubric: Again 20, Hard 70, Good 85, Easy 100.
"""

from __future__ import annotations

from dataclasses import dataclass

from banana_english.domain.models import (
    Assessment,
    Assessor,
    Exercise,
    Mistake,
    MistakeCategory,
    SrsRating,
)
from banana_english.domain.services.answer_matching import (
    edit_distance,
    matches_any,
    normalize_answer,
)

RATING_SCORE = {
    SrsRating.AGAIN: 20.0,
    SrsRating.HARD: 70.0,
    SrsRating.GOOD: 85.0,
    SrsRating.EASY: 100.0,
}
_ORDER = [SrsRating.AGAIN, SrsRating.HARD, SrsRating.GOOD, SrsRating.EASY]


@dataclass(frozen=True)
class CardReview:
    rating: SrsRating  # effective rating after the typed-answer cap
    assessment: Assessment


def _typo_budget(target: str) -> int:
    if len(target) >= 8:
        return 2
    return 1 if len(target) >= 4 else 0


def check_typed_answer(exercise: Exercise, answer: str) -> tuple[SrsRating, Mistake | None]:
    """Return the maximum rating the typed answer allows, and the mistake if any."""
    target = exercise.accepted_answers[0]
    normalized = normalize_answer(answer)
    if not normalized:
        return SrsRating.AGAIN, Mistake(
            MistakeCategory.NO_ANSWER, "No word was typed.", correction=target
        )
    if matches_any(answer, exercise.accepted_answers):
        return SrsRating.EASY, None
    for accepted in exercise.accepted_answers:
        reference = normalize_answer(accepted)
        budget = _typo_budget(reference)
        if budget and edit_distance(normalized, reference) <= budget:
            return SrsRating.HARD, Mistake(
                MistakeCategory.SPELLING,
                "The word is misspelled.",
                fragment=answer.strip(),
                correction=accepted,
            )
    return SrsRating.AGAIN, Mistake(
        MistakeCategory.WRONG_WORD,
        "This word does not match the definition.",
        fragment=answer.strip(),
        correction=target,
    )


def review(exercise: Exercise, rating: SrsRating, answer: str | None) -> CardReview:
    target = exercise.accepted_answers[0]
    mistake = None
    assessor = Assessor.SELF_RATED
    if answer is not None:
        assessor = Assessor.DETERMINISTIC
        cap, mistake = check_typed_answer(exercise, answer)
        rating = min(rating, cap, key=_ORDER.index)
    score = RATING_SCORE[rating]
    feedback = {
        SrsRating.AGAIN: f"Let's see this one again soon. The word is '{target}'.",
        SrsRating.HARD: f"Almost — '{target}'. It will come back soon.",
        SrsRating.GOOD: f"Good! '{target}'.",
        SrsRating.EASY: f"Easy! '{target}'.",
    }[rating]
    return CardReview(
        rating=rating,
        assessment=Assessment(
            score=score,
            is_correct=rating.quality >= 3,
            feedback=feedback,
            assessor=assessor,
            mistakes=(mistake,) if mistake else (),
            corrected_answer=target if mistake else None,
        ),
    )
