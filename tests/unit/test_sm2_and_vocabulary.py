"""Phase 2 DoD: Again vs Easy must diverge correctly over many simulated days."""

from datetime import UTC, datetime, timedelta

import pytest

from banana_english.application.services.vocabulary_assessment import RATING_SCORE, review
from banana_english.domain.models import (
    CefrLevel,
    ContentReviewStatus,
    MistakeCategory,
    SrsRating,
    VocabularyCard,
    VocabularyItem,
)
from banana_english.domain.services.answer_matching import edit_distance, normalize_answer
from banana_english.domain.services.sm2 import MIN_EASE, is_due, review_card
from banana_english.domain.services.vocabulary_exercises import BLANK, build_recall_exercise

T = datetime(2026, 1, 1, 8, tzinfo=UTC)


def simulate(rating: SrsRating, days: int = 90):
    """Review the card every time it is due, always pressing the same button."""
    card, now, reviews = VocabularyCard("l", "apple.noun", created_at=T), T, []
    while now < T + timedelta(days=days):
        if is_due(card, now.date()):
            card = review_card(card, rating.quality, now)
            reviews.append((now.date(), card.interval_days))
        now += timedelta(days=1)
    return card, reviews


def test_quality_mapping_matches_anki_buttons():
    assert [r.quality for r in SrsRating] == [1, 3, 4, 5]


def test_first_intervals_are_1_then_6_days():
    card = review_card(VocabularyCard("l", "x"), 4, T)
    assert card.interval_days == 1 and card.due_date == (T + timedelta(days=1)).date()
    card = review_card(card, 4, T + timedelta(days=1))
    assert card.interval_days == 6
    card = review_card(card, 4, T + timedelta(days=7))
    assert card.interval_days == round(6 * card.ease_factor)


def test_again_vs_easy_diverge_over_90_simulated_days():
    again_card, again_reviews = simulate(SrsRating.AGAIN)
    easy_card, easy_reviews = simulate(SrsRating.EASY)
    # "Again" keeps the card daily; "Easy" pushes it out exponentially.
    assert {interval for _, interval in again_reviews} == {1}
    assert len(again_reviews) == 90
    assert len(easy_reviews) <= 6
    assert [i for _, i in easy_reviews][:3] == [1, 6, 16]
    assert easy_card.interval_days > 60
    assert again_card.ease_factor == MIN_EASE and easy_card.ease_factor > 2.5
    assert again_card.lapses == 90 and easy_card.lapses == 0


def test_good_and_hard_sit_between():
    good = simulate(SrsRating.GOOD)[0].interval_days
    hard = simulate(SrsRating.HARD)[0].interval_days
    easy = simulate(SrsRating.EASY)[0].interval_days
    assert 1 < hard < good < easy


def test_lapse_resets_repetitions():
    card = review_card(review_card(VocabularyCard("l", "x"), 5, T), 5, T)
    card = review_card(card, 1, T)
    assert (card.repetitions, card.interval_days, card.lapses) == (0, 1, 1)


def test_quality_range():
    with pytest.raises(ValueError):
        review_card(VocabularyCard("l", "x"), 6, T)


# --- typed answer + rating ---------------------------------------------------------------


def item(word="behaviour", variants=("behavior",), example="his behaviour was good"):
    return VocabularyItem(
        f"{word}.noun",
        word,
        variants,
        "noun",
        CefrLevel.A2,
        "the way a person acts",
        example,
        ContentReviewStatus.AUTO_MAPPED,
    )


@pytest.mark.parametrize("answer", ["behaviour", " Behaviour ", "BEHAVIOUR.", "behavior"])
def test_correct_typed_answer_keeps_rating(answer):
    r = review(build_recall_exercise(item()), SrsRating.EASY, answer)
    assert r.rating is SrsRating.EASY and r.assessment.score == 100 and r.assessment.is_correct


def test_typo_caps_rating_at_hard():
    r = review(build_recall_exercise(item()), SrsRating.EASY, "behavoiur")
    assert r.rating is SrsRating.HARD
    assert r.assessment.mistakes[0].category is MistakeCategory.SPELLING


@pytest.mark.parametrize(
    "answer,category", [("attitude", MistakeCategory.WRONG_WORD), ("", MistakeCategory.NO_ANSWER)]
)
def test_wrong_typed_answer_forces_again(answer, category):
    r = review(build_recall_exercise(item()), SrsRating.EASY, answer)
    assert r.rating is SrsRating.AGAIN and not r.assessment.is_correct
    assert r.assessment.mistakes[0].category is category


def test_self_rating_without_typing():
    r = review(build_recall_exercise(item()), SrsRating.HARD, None)
    assert r.assessment.score == RATING_SCORE[SrsRating.HARD] == 70
    assert r.assessment.assessor.value == "self_rated"


def test_card_front_hides_the_word():
    ex = build_recall_exercise(item(example="His Behaviour (and behavior) was good"))
    assert "behavio" not in ex.prompt.lower() and ex.prompt.count(BLANK) == 2
    assert ex.hint == "Starts with 'b', 9 letters"


def test_normalization_and_distance():
    assert normalize_answer("  It’s   FINE!! ") == "it's fine"
    assert edit_distance("kitten", "sitting") == 3
