from __future__ import annotations

from datetime import datetime, time

from banana_english.application.use_cases.common import UowFactory, require_learner
from banana_english.domain.interfaces.infra import Clock
from banana_english.domain.interfaces.recommendation import (
    RecommendationContext,
    RecommendationEngine,
)
from banana_english.domain.interfaces.repositories import UnitOfWork
from banana_english.domain.models import Recommendation

MAX_DUE_CARDS = 100


def start_of_day(now: datetime) -> datetime:
    return datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)


def build_context(
    uow: UnitOfWork, learner_id: str, now: datetime, daily_new_cards: int
) -> RecommendationContext:
    _, profile = require_learner(uow, learner_id)
    created_today = uow.cards.created_since(learner_id, start_of_day(now))
    return RecommendationContext(
        profile=profile,
        now=now,
        masteries={m.skill_id: m for m in uow.mastery.list(learner_id)},
        item_history=uow.attempts.item_history(learner_id),
        due_card_ids=tuple(
            c.item_id for c in uow.cards.list_due(learner_id, now.date(), MAX_DUE_CARDS)
        ),
        new_cards_available=max(0, daily_new_cards - created_today),
        mistake_counts=uow.attempts.recent_mistake_counts(learner_id),
    )


class GetRecommendations:
    def __init__(
        self,
        uow_factory: UowFactory,
        engine: RecommendationEngine,
        clock: Clock,
        daily_new_cards: int = 10,
    ) -> None:
        self._uow_factory = uow_factory
        self._engine = engine
        self._clock = clock
        self._daily_new_cards = daily_new_cards

    def execute(self, learner_id: str, n: int = 5) -> tuple[list[Recommendation], datetime]:
        now = self._clock.now()
        with self._uow_factory() as uow:
            context = build_context(uow, learner_id, now, self._daily_new_cards)
        return self._engine.next_exercises(context, n), now

    def first(self, learner_id: str) -> Recommendation | None:
        recs, _ = self.execute(learner_id, 1)
        return recs[0] if recs else None
