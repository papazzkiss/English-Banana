"""Learner profile, mastery and dashboard queries (Phases 4 and 10)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from banana_english.application.use_cases.common import UowFactory, require_learner
from banana_english.domain.interfaces.infra import Clock
from banana_english.domain.interfaces.repositories import ContentRepository
from banana_english.domain.models import (
    Attempt,
    LearnerProfile,
    MasteryEvent,
    Skill,
    SkillMastery,
    User,
)
from banana_english.domain.services.mastery import (
    WEAKNESS_THRESHOLD,
    effective_mastery,
    initial_mastery,
)
from banana_english.domain.services.roadmap import (
    LevelMilestone,
    SkillProgress,
    roadmap_levels,
)
from banana_english.domain.services.weakness import WeakSkill, find_weak_skills


@dataclass(frozen=True)
class LearnerOverview:
    user: User
    profile: LearnerProfile
    total_attempts: int
    correct_attempts: int


@dataclass(frozen=True)
class SkillMasteryView:
    skill: Skill
    mastery: SkillMastery
    effective: float
    is_weak: bool


@dataclass(frozen=True)
class ActivitySummary:
    days: list[tuple[date, int]]  # oldest first, including zero days
    active_days: int
    current_streak: int


class LearnerQueries:
    def __init__(self, uow_factory: UowFactory, content: ContentRepository, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._content = content
        self._clock = clock

    def profile(self, learner_id: str) -> LearnerOverview:
        with self._uow_factory() as uow:
            user, profile = require_learner(uow, learner_id)
            total, correct = uow.attempts.count(learner_id)
        return LearnerOverview(user, profile, total, correct)

    def mastery(self, learner_id: str) -> list[SkillMasteryView]:
        now = self._clock.now()
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            stored = {m.skill_id: m for m in uow.mastery.list(learner_id)}
        views = []
        for skill in self._content.list_skills():
            m = stored.get(skill.id) or initial_mastery(learner_id, skill.id)
            eff = effective_mastery(m, now)
            views.append(
                SkillMasteryView(skill, m, eff, m.attempt_count > 0 and eff < WEAKNESS_THRESHOLD)
            )
        return views

    def weak_skills(self, learner_id: str, limit: int = 5) -> list[WeakSkill]:
        """Same function the recommender uses — the dashboard can never disagree with it."""
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            masteries = uow.mastery.list(learner_id)
        return find_weak_skills(masteries, self._clock.now(), limit)

    def mastery_history(
        self, learner_id: str, skill_id: str | None = None, days: int = 30
    ) -> list[MasteryEvent]:
        since = self._clock.now() - timedelta(days=days)
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            return uow.mastery.events(learner_id, since, skill_id)

    def activity(self, learner_id: str, days: int = 7) -> ActivitySummary:
        today = self._clock.now().date()
        start = today - timedelta(days=days - 1)
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            counts = uow.mastery.active_days(
                learner_id,
                datetime.combine(start, datetime.min.time(), tzinfo=self._clock.now().tzinfo),
            )
            streak_counts = uow.mastery.active_days(
                learner_id, self._clock.now() - timedelta(days=366)
            )
        series = [
            (start + timedelta(days=i), counts.get(start + timedelta(days=i), 0))
            for i in range(days)
        ]
        streak, day = 0, today
        if streak_counts.get(day, 0) == 0:
            day -= timedelta(days=1)  # today not practised yet: streak still alive
        while streak_counts.get(day, 0) > 0:
            streak += 1
            day -= timedelta(days=1)
        return ActivitySummary(series, sum(1 for _, n in series if n), streak)

    def roadmap(self, learner_id: str) -> tuple[LearnerProfile, list[LevelMilestone]]:
        """CEFR milestones from A1 to the learner's target, with the skills and words each
        level needs (see domain/services/roadmap.py for the estimate)."""
        views = self.mastery(learner_id)
        with self._uow_factory() as uow:
            _, profile = require_learner(uow, learner_id)
            seen = uow.cards.seen_item_ids(learner_id)
        levels = []
        for level in roadmap_levels(profile.current_level, profile.target_level):
            words = self._content.list_vocabulary(f"vocabulary.{level.value.lower()}")
            levels.append(
                LevelMilestone(
                    level=level,
                    skills=tuple(
                        SkillProgress(
                            v.skill.id,
                            v.skill.name,
                            v.skill.module,
                            v.effective,
                            v.mastery.attempt_count,
                        )
                        for v in views
                        if v.skill.entry_level is level
                    ),
                    words_total=len(words),
                    words_started=sum(1 for w in words if w.id in seen),
                )
            )
        return profile, levels

    def attempted_item_ids(self, learner_id: str) -> set[str]:
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            return set(uow.attempts.item_history(learner_id))

    def recent_attempts(self, learner_id: str, limit: int = 20) -> list[Attempt]:
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            return uow.attempts.recent(learner_id, limit)
