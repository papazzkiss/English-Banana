"""Per-skill mastery: an exponential moving average (EMA) on the unified 0-100 rubric.

    mastery_new = alpha * score + (1 - alpha) * mastery_old        (starts at 50)

* ALPHA = 0.3: the latest attempt carries 30% of the weight. It is a starting point,
  not a proven constant — tune it from real learner curves (see docs/phases.md, Phase 4).
* Anti-gaming: repeating an item the learner already answered correctly uses
  REPEAT_ALPHA = 0.1, so drilling one easy exercise cannot inflate mastery.
* confidence = share of the EMA weight that comes from real attempts rather than the
  default 50:  confidence_new = 1 - (1 - confidence_old) * (1 - alpha).
* Forgetting (read-time only, never stored): after a 7-day grace period, mastery above
  50 decays back toward 50 with a 30-day half-life, so stale "strong" skills resurface.

Everything here is pure and deterministic; replaying the attempt log reproduces the state.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime

from banana_english.domain.models import SkillMastery


@dataclass(frozen=True)
class MasteryParams:
    alpha: float = 0.3
    repeat_alpha: float = 0.1
    default_mastery: float = 50.0
    decay_grace_days: float = 7.0
    decay_half_life_days: float = 30.0

    def __post_init__(self) -> None:
        if not 0.0 < self.alpha <= 1.0 or not 0.0 < self.repeat_alpha <= self.alpha:
            raise ValueError("require 0 < repeat_alpha <= alpha <= 1")
        if not 0.0 <= self.default_mastery <= 100.0:
            raise ValueError("default_mastery must be within [0, 100]")
        if self.decay_half_life_days <= 0 or self.decay_grace_days < 0:
            raise ValueError("invalid decay parameters")


DEFAULT_PARAMS = MasteryParams()

WEAKNESS_THRESHOLD = 60.0  # below this a skill is "weak" (recommendation + dashboard)
EASY_BELOW = 40.0  # weak skills below this get easy material, otherwise medium


def initial_mastery(
    learner_id: str, skill_id: str, params: MasteryParams = DEFAULT_PARAMS
) -> SkillMastery:
    return SkillMastery(
        learner_id=learner_id,
        skill_id=skill_id,
        mastery=params.default_mastery,
        confidence=0.0,
        attempt_count=0,
        correct_count=0,
        last_practiced_at=None,
    )


def update_mastery(
    current: SkillMastery,
    *,
    score: float,
    is_correct: bool,
    practiced_at: datetime,
    repeat: bool = False,
    params: MasteryParams = DEFAULT_PARAMS,
) -> SkillMastery:
    """New state after one assessed attempt. `repeat`: item already answered correctly before."""
    if not 0.0 <= score <= 100.0:
        raise ValueError(f"score must be within [0, 100], got {score}")
    alpha = params.repeat_alpha if repeat else params.alpha
    return replace(
        current,
        mastery=alpha * score + (1.0 - alpha) * current.mastery,
        confidence=1.0 - (1.0 - current.confidence) * (1.0 - alpha),
        attempt_count=current.attempt_count + 1,
        correct_count=current.correct_count + (1 if is_correct else 0),
        last_practiced_at=practiced_at,
    )


def replay_mastery(
    learner_id: str,
    skill_id: str,
    history: Iterable[tuple[float, bool, datetime, bool]],
    params: MasteryParams = DEFAULT_PARAMS,
) -> SkillMastery:
    """Recompute from (score, is_correct, at, repeat) tuples, oldest first."""
    state = initial_mastery(learner_id, skill_id, params)
    for score, is_correct, at, repeat in history:
        state = update_mastery(
            state, score=score, is_correct=is_correct, practiced_at=at, repeat=repeat, params=params
        )
    return state


def effective_mastery(
    mastery: SkillMastery, now: datetime, params: MasteryParams = DEFAULT_PARAMS
) -> float:
    """Mastery adjusted for forgetting. Only decays values above the default, toward it."""
    if mastery.last_practiced_at is None or mastery.mastery <= params.default_mastery:
        return mastery.mastery
    idle_days = (now - mastery.last_practiced_at).total_seconds() / 86400.0
    if idle_days <= params.decay_grace_days:
        return mastery.mastery
    factor = 0.5 ** ((idle_days - params.decay_grace_days) / params.decay_half_life_days)
    return params.default_mastery + (mastery.mastery - params.default_mastery) * factor


def is_weak(mastery: SkillMastery, now: datetime) -> bool:
    return mastery.attempt_count > 0 and effective_mastery(mastery, now) < WEAKNESS_THRESHOLD
