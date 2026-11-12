"""Phase 2: SM-2 review queue."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from banana_english.application.services.vocabulary_assessment import review
from banana_english.application.use_cases.common import (
    AttemptOutcome,
    NotFoundError,
    UowFactory,
    record_mastery,
    require_learner,
)
from banana_english.application.use_cases.recommendations import (
    GetRecommendations,
    start_of_day,
)
from banana_english.domain.interfaces.infra import Clock
from banana_english.domain.interfaces.repositories import ContentRepository
from banana_english.domain.models import (
    Attempt,
    AttemptStatus,
    Exercise,
    Module,
    SrsRating,
    VocabularyCard,
    VocabularyItem,
)
from banana_english.domain.services.sm2 import review_card
from banana_english.domain.services.vocabulary_exercises import build_recall_exercise


@dataclass(frozen=True)
class DueCard:
    item: VocabularyItem
    exercise: Exercise  # front of the card (definition + blanked example)
    card: VocabularyCard | None  # None = new card
    is_new: bool


class VocabularyReview:
    def __init__(
        self,
        uow_factory: UowFactory,
        content: ContentRepository,
        clock: Clock,
        recommendations: GetRecommendations,
        daily_new_cards: int = 10,
    ) -> None:
        self._uow_factory = uow_factory
        self._content = content
        self._clock = clock
        self._recommendations = recommendations
        self._daily_new_cards = daily_new_cards

    def due(self, learner_id: str, limit: int = 20) -> list[DueCard]:
        """Cards due today (most overdue first), then new cards up to the daily limit."""
        now = self._clock.now()
        with self._uow_factory() as uow:
            _, profile = require_learner(uow, learner_id)
            due = uow.cards.list_due(learner_id, now.date(), limit)
            seen = uow.cards.seen_item_ids(learner_id)
            new_left = max(
                0, self._daily_new_cards - uow.cards.created_since(learner_id, start_of_day(now))
            )
        result = []
        for card in due:
            item = self._content.get_vocabulary_item(card.item_id)
            if item:
                result.append(DueCard(item, build_recall_exercise(item), card, False))
        room = min(new_left, limit - len(result))
        if room > 0:
            level = profile.current_level
            while level is not None and room > 0:
                for item in self._content.list_vocabulary(f"vocabulary.{level.value.lower()}"):
                    if room == 0:
                        break
                    if item.id not in seen:
                        result.append(DueCard(item, build_recall_exercise(item), None, True))
                        room -= 1
                level = level.next()
        return result

    def review(
        self,
        learner_id: str,
        card_id: str,
        rating: SrsRating,
        answer: str | None = None,
        response_time_ms: int | None = None,
    ) -> AttemptOutcome:
        item = self._content.get_vocabulary_item(card_id)
        if item is None:
            raise NotFoundError(f"card {card_id}")
        exercise = build_recall_exercise(item)
        result = review(exercise, rating, answer)
        now = self._clock.now()
        attempt_id = str(uuid.uuid4())
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            card = uow.cards.get(learner_id, item.id) or VocabularyCard(
                learner_id, item.id, created_at=now
            )
            # Anti-gaming: re-reviewing a card before it is due counts with the low repeat weight.
            early = card.due_date is not None and card.due_date > now.date()
            updated = review_card(card, result.rating.quality, now)
            uow.cards.save(updated)
            uow.attempts.add(
                Attempt(
                    attempt_id,
                    learner_id,
                    Module.VOCABULARY,
                    item.id,
                    item.skill_id,
                    answer if answer is not None else f"[{rating.value}]",
                    now,
                    AttemptStatus.ASSESSED,
                    response_time_ms,
                    result.assessment,
                    {"rating": result.rating.value, "pressed": rating.value},
                )
            )
            change = record_mastery(
                uow,
                learner_id,
                item.skill_id,
                score=result.assessment.score,
                is_correct=result.assessment.is_correct,
                at=now,
                attempt_id=attempt_id,
                repeat=early,
            )
            uow.commit()
        return AttemptOutcome(
            attempt_id,
            item.id,
            item.skill_id,
            now,
            result.assessment,
            [change],
            self._recommendations.first(learner_id),
            {"card": updated, "item": item, "rating": result.rating},
        )
