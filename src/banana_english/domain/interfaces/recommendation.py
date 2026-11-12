from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime

from banana_english.domain.models import LearnerProfile, Recommendation, SkillMastery


@dataclass(frozen=True)
class ItemHistory:
    attempts: int
    last_correct: bool
    last_attempted_at: datetime
    ever_correct: bool = False


@dataclass(frozen=True)
class RecommendationContext:
    """Everything the engine may look at. Built by the application layer; no I/O inside."""

    profile: LearnerProfile
    now: datetime
    masteries: Mapping[str, SkillMastery]  # skill_id -> mastery (missing = never practised)
    item_history: Mapping[str, ItemHistory]  # item id -> history (exercise, question, prompt...)
    due_card_ids: tuple[str, ...]  # SM-2 cards due today, most overdue first
    new_cards_available: int  # new vocabulary cards allowed today (daily limit)
    mistake_counts: Mapping[str, Mapping[str, int]] = field(default_factory=dict)

    @property
    def today(self) -> date:
        return self.now.date()


class RecommendationEngine(ABC):
    """The component most likely to be replaced by ML (bandit / ranking model).
    Callers only know next_exercises(); swapping the strategy touches one file."""

    @abstractmethod
    def next_exercises(self, context: RecommendationContext, n: int = 5) -> list[Recommendation]:
        """Return at most n recommendations, most important first. Never empty for a
        learner with content available (cold start is handled by a default mix)."""
