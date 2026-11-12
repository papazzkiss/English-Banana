from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from banana_english.application.services.recommendation_engine import (
    RuleBasedRecommendationEngine,
    target_difficulty,
)
from banana_english.domain.interfaces.recommendation import ItemHistory, RecommendationContext
from banana_english.domain.models import (
    CefrLevel,
    Difficulty,
    LearnerProfile,
    Module,
    RecommendationKind,
)
from banana_english.domain.services.mastery import initial_mastery

NOW = datetime(2026, 3, 1, 9, tzinfo=UTC)


def mastery(skill_id, value, attempts=4, days_ago=1):
    return replace(
        initial_mastery("l", skill_id),
        mastery=value,
        attempt_count=attempts,
        last_practiced_at=NOW - timedelta(days=days_ago),
    )


def ctx(masteries=(), level=CefrLevel.A1, history=None, due=(), new=10, mistakes=None):
    return RecommendationContext(
        profile=LearnerProfile("l", level, CefrLevel.B2, "vi", NOW),
        now=NOW,
        masteries={m.skill_id: m for m in masteries},
        item_history=history or {},
        due_card_ids=tuple(due),
        new_cards_available=new,
        mistake_counts=mistakes or {},
    )


@pytest.fixture
def engine(content):
    return RuleBasedRecommendationEngine(content)


def by_skill(recs):
    return {r.skill_id: r for r in recs}


def test_cold_start_default_mix_covers_every_module(engine):
    recs = engine.next_exercises(ctx(), 5)
    assert len(recs) == 5
    assert all(r.kind is RecommendationKind.NEW_TOPIC for r in recs)
    assert [r.module for r in recs] == [
        Module.VOCABULARY,
        Module.GRAMMAR,
        Module.LISTENING,
        Module.SPEAKING,
        Module.CONVERSATION,
    ]
    assert recs[1].items[0].difficulty is Difficulty.EASY


def test_new_topics_respect_learner_level(engine):
    skills = {r.skill_id for r in engine.next_exercises(ctx(level=CefrLevel.A1), 10)}
    assert "vocabulary.a1" in skills and "vocabulary.b1" not in skills
    assert "grammar.conditionals" not in skills  # B1 topic for an A1 learner


def test_weak_skills_come_first_weakest_first(engine):
    c = ctx(
        [
            mastery("grammar.articles", 55),
            mastery("grammar.prepositions_time_place", 30),
            mastery("vocabulary.a1", 90),
        ]
    )
    recs = engine.next_exercises(c, 5)
    assert [r.skill_id for r in recs[:2]] == ["grammar.prepositions_time_place", "grammar.articles"]
    assert all(r.kind is RecommendationKind.REINFORCEMENT for r in recs[:2])
    assert recs[0].reason_code == "weak_skill" and recs[0].priority == 1


@pytest.mark.parametrize(
    ("value", "difficulty"),
    [
        (20, Difficulty.EASY),
        (39.9, Difficulty.EASY),
        (40, Difficulty.MEDIUM),
        (59, Difficulty.MEDIUM),
    ],
)
def test_weak_skill_difficulty(engine, value, difficulty):
    rec = by_skill(engine.next_exercises(ctx([mastery("grammar.articles", value)]), 5))
    assert rec["grammar.articles"].evidence["difficulty"] == difficulty.value
    assert rec["grammar.articles"].items[0].difficulty is difficulty


def test_target_difficulty_bands():
    assert [target_difficulty(x) for x in (10, 50, 85)] == [
        Difficulty.EASY,
        Difficulty.MEDIUM,
        Difficulty.HARD,
    ]


def test_at_most_three_weak_skills(engine):
    weak = [
        mastery(s, 30)
        for s in (
            "grammar.articles",
            "grammar.prepositions_time_place",
            "grammar.comparatives_superlatives",
            "grammar.present_simple_continuous",
        )
    ]
    recs = engine.next_exercises(ctx(weak), 10)
    assert sum(r.kind is RecommendationKind.REINFORCEMENT for r in recs) == 3


def test_failing_past_tense_recommends_past_tense(engine):
    """Phase 5 DoD scenario at the engine level."""
    history = {"gr.past.001": ItemHistory(1, False, NOW - timedelta(minutes=5))}
    c = ctx(
        [mastery("grammar.past_simple_present_perfect", 29)],
        level=CefrLevel.A2,
        history=history,
        mistakes={"grammar.past_simple_present_perfect": {"verb_tense": 3}},
    )
    top = engine.next_exercises(c, 5)[0]
    assert top.skill_id == "grammar.past_simple_present_perfect"
    assert top.kind is RecommendationKind.REINFORCEMENT
    assert "verb tense" in top.reason
    assert "gr.past.001" not in [i.item_id for i in top.items]  # not the item just attempted


def test_unseen_before_failed_before_passed(engine, content):
    easy = [
        e.id for e in content.list_exercises("grammar.articles") if e.difficulty.value == "easy"
    ]
    history = {
        easy[0]: ItemHistory(1, True, NOW - timedelta(days=3)),
        easy[1]: ItemHistory(1, False, NOW - timedelta(days=2)),
        # most recent attempt is on another (medium) item, which is excluded
        "gr.articles.004": ItemHistory(1, False, NOW - timedelta(hours=1)),
    }
    rec = by_skill(
        engine.next_exercises(ctx([mastery("grammar.articles", 30)], history=history), 5)
    )["grammar.articles"]
    assert [i.item_id for i in rec.items] == [easy[2], easy[1]]  # unseen, then failed


def test_due_cards_after_weak_skills_before_new_topics(engine):
    recs = engine.next_exercises(
        ctx([mastery("grammar.articles", 30)], due=["apple.noun", "book.noun"]), 5
    )
    assert [r.kind for r in recs[:3]] == [
        RecommendationKind.REINFORCEMENT,
        RecommendationKind.REVIEW,
        RecommendationKind.NEW_TOPIC,
    ]
    assert [i.item_id for i in recs[1].items] == ["apple.noun", "book.noun"]


def test_no_new_cards_when_daily_limit_reached(engine):
    recs = by_skill(engine.next_exercises(ctx(new=0), 10))
    assert "vocabulary.a1" not in recs


def test_practice_fills_list_when_nothing_is_weak(engine):
    strong = [
        mastery(s.id, 90, days_ago=2)
        for s in engine._content.list_skills()
        if s.module is not Module.VOCABULARY or s.id == "vocabulary.a1"
    ]
    recs = engine.next_exercises(ctx(strong, new=0), 3)
    assert recs and all(r.kind is RecommendationKind.PRACTICE for r in recs)


def test_deterministic_and_unique(engine):
    c = ctx([mastery("grammar.articles", 30), mastery("vocabulary.a1", 45)], due=["apple.noun"])
    recs = engine.next_exercises(c, 6)
    assert recs == engine.next_exercises(c, 6)
    assert len({r.skill_id for r in recs}) == len(recs)
    assert [r.priority for r in recs] == list(range(1, len(recs) + 1))


def test_speaking_stays_at_the_learners_level(engine):
    """A1 learner, weak spoken grammar, the A1 prompt answered wrongly once: it is still
    preferred over an unseen A2 prompt (above-level material only when nothing else is left)."""
    weak = mastery("speaking.grammar", 25, attempts=2)
    history = {
        "sp.intro.001": ItemHistory(1, False, NOW - timedelta(hours=2), False),
        "sp.hometown.001": ItemHistory(1, False, NOW - timedelta(hours=1), False),
    }
    recs = engine.next_exercises(ctx([weak], level=CefrLevel.A1, history=history), 5)
    speaking = by_skill(recs)["speaking.grammar"]
    assert [i.item_id for i in speaking.items] == ["sp.intro.001"]


def test_reinforcement_reason_explains_the_issue_and_the_next_step(engine):
    weak = mastery("speaking.grammar", 25, attempts=2)
    recs = engine.next_exercises(
        ctx([weak], mistakes={"speaking.grammar": {"incomplete_answer": 2}}), 5
    )
    reason = by_skill(recs)["speaking.grammar"].reason
    assert "incomplete answer: the answer left out part of the task (e.g." in reason
    assert "Answer one speaking prompt out loud" in reason


def test_vocabulary_word_count_matches_the_session(engine):
    recs = engine.next_exercises(ctx(due=["ghost.noun", "social.adjective"], new=10), 5)
    review = next(r for r in recs if r.kind is RecommendationKind.REVIEW)
    new = next(r for r in recs if r.module is Module.VOCABULARY and r is not review)
    assert review.evidence["word_count"] == 2
    assert new.evidence["word_count"] == 10  # the 10 new cards the session will show
    assert len(new.items) <= 8  # items stay a short preview


def test_weak_vocabulary_counts_only_words_the_session_shows(engine):
    """A word answered wrongly but not due until tomorrow is not in today's session."""
    weak = mastery("vocabulary.a1", 30)
    history = {"ghost.noun": ItemHistory(1, False, NOW - timedelta(hours=1), False)}
    rec = by_skill(engine.next_exercises(ctx([weak], history=history, new=4), 5))["vocabulary.a1"]
    assert rec.evidence["word_count"] == 4
    assert "ghost.noun" not in [i.item_id for i in rec.items]
    due = engine.next_exercises(ctx([weak], history=history, due=["ghost.noun"], new=4), 5)
    assert by_skill(due)["vocabulary.a1"].items[0].item_id == "ghost.noun"
