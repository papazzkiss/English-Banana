"""Weakness detection — ONE function shared by the recommender and the dashboard, so the
"weak skills" a learner sees are exactly the ones driving their next exercises."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from banana_english.domain.models import SkillMastery
from banana_english.domain.services.mastery import WEAKNESS_THRESHOLD, effective_mastery


@dataclass(frozen=True)
class WeakSkill:
    mastery: SkillMastery
    effective: float  # after forgetting decay


def find_weak_skills(
    masteries: Iterable[SkillMastery], now: datetime, limit: int = 3
) -> list[WeakSkill]:
    """Practised skills with effective mastery < WEAKNESS_THRESHOLD, weakest first."""
    weak = [
        WeakSkill(m, effective_mastery(m, now))
        for m in masteries
        if m.attempt_count > 0 and effective_mastery(m, now) < WEAKNESS_THRESHOLD
    ]
    weak.sort(key=lambda w: (w.effective, w.mastery.skill_id))
    return weak[:limit]
