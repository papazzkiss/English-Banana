from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from banana_english.domain.services.mastery import (
    WEAKNESS_THRESHOLD,
    MasteryParams,
    effective_mastery,
    initial_mastery,
    is_weak,
    replay_mastery,
    update_mastery,
)
from banana_english.domain.services.weakness import find_weak_skills

T = datetime(2026, 1, 1, tzinfo=UTC)


def run(scores, repeat=False):
    state = initial_mastery("l", "s")
    for i, score in enumerate(scores):
        state = update_mastery(
            state,
            score=score,
            is_correct=score >= 70,
            practiced_at=T + timedelta(minutes=i),
            repeat=repeat,
        )
    return state


def test_initial_state():
    m = initial_mastery("l", "s")
    assert (m.mastery, m.confidence, m.attempt_count, m.last_practiced_at) == (50.0, 0.0, 0, None)


def test_ema_formula_with_alpha_0_3():
    assert run([100]).mastery == pytest.approx(0.3 * 100 + 0.7 * 50)  # 65
    assert run([20]).mastery == pytest.approx(0.3 * 20 + 0.7 * 50)  # 41
    assert run([100, 0]).mastery == pytest.approx(0.3 * 0 + 0.7 * 65)


def test_counters_and_timestamp():
    m = run([100, 20, 85])
    assert (m.attempt_count, m.correct_count) == (3, 2)
    assert m.last_practiced_at == T + timedelta(minutes=2)


def test_confidence_is_share_of_weight_from_attempts():
    assert run([80]).confidence == pytest.approx(0.3)
    assert run([80, 80]).confidence == pytest.approx(1 - 0.7**2)
    assert run([80] * 30).confidence < 1.0


def test_recent_attempts_dominate():
    assert run([0] * 5 + [100] * 5).mastery > run([100] * 5 + [0] * 5).mastery


def test_single_bad_attempt_makes_fresh_skill_weak():
    assert run([20]).mastery < WEAKNESS_THRESHOLD


def test_repeat_alpha_limits_gaming():
    """Re-doing an already-correct item moves mastery far less than new items."""
    drilled = run([100] * 3, repeat=True).mastery  # 50 + (1 - 0.9^3) * 50 = 63.6
    varied = run([100] * 3).mastery  # 50 + (1 - 0.7^3) * 50 = 82.9
    assert drilled < WEAKNESS_THRESHOLD + 5 < varied


def test_replay_equals_incremental_and_is_deterministic():
    scores = [100, 20, 85, 0, 70]
    history = [(s, s >= 70, T + timedelta(minutes=i), False) for i, s in enumerate(scores)]
    assert replay_mastery("l", "s", history) == run(scores) == run(scores)


def test_bounds():
    for m in (run([100] * 200), run([0] * 200)):
        assert 0.0 <= m.mastery <= 100.0 and 0.0 <= m.confidence <= 1.0


def test_forgetting_decay_only_above_default_and_after_grace_period():
    strong = run([100] * 10)  # ~98.6
    assert effective_mastery(strong, strong.last_practiced_at + timedelta(days=7)) == strong.mastery
    later = effective_mastery(strong, strong.last_practiced_at + timedelta(days=37))
    assert later == pytest.approx(50 + (strong.mastery - 50) * 0.5)  # one half-life
    weak = run([0])
    assert effective_mastery(weak, weak.last_practiced_at + timedelta(days=90)) == weak.mastery


def test_stale_strong_skill_resurfaces_as_weak():
    m = replace(run([100] * 3), mastery=65.0)
    assert not is_weak(m, m.last_practiced_at + timedelta(days=5))
    assert is_weak(m, m.last_practiced_at + timedelta(days=120))


def test_find_weak_skills_orders_weakest_first_and_ignores_unpractised():
    a, b = replace(run([20]), skill_id="a"), replace(run([0, 0]), skill_id="b")
    c = replace(run([100]), skill_id="c")
    fresh = initial_mastery("l", "d")
    weak = find_weak_skills([a, b, c, fresh], T + timedelta(days=1), limit=3)
    assert [w.mastery.skill_id for w in weak] == ["b", "a"]


@pytest.mark.parametrize("score", [-1, 101])
def test_rejects_out_of_range(score):
    with pytest.raises(ValueError):
        update_mastery(initial_mastery("l", "s"), score=score, is_correct=False, practiced_at=T)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"alpha": 0},
        {"alpha": 0.2, "repeat_alpha": 0.3},
        {"default_mastery": 120},
        {"decay_half_life_days": 0},
    ],
)
def test_invalid_params(kwargs):
    with pytest.raises(ValueError):
        MasteryParams(**kwargs)
