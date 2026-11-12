"""SM-2 spaced repetition (the algorithm behind Anki), as a pure function.

quality 0-5 comes from Anki-style buttons: Again=1, Hard=3, Good=4, Easy=5.
* quality < 3  -> repetitions reset, review again tomorrow, lapse counted
* quality >= 3 -> interval 1 day, then 6 days, then interval * ease_factor
* ease_factor += 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02), floored at 1.3
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

from banana_english.domain.models import VocabularyCard

MIN_EASE = 1.3


def review_card(card: VocabularyCard, quality: int, now: datetime) -> VocabularyCard:
    if not 0 <= quality <= 5:
        raise ValueError(f"quality must be within 0..5, got {quality}")
    repetitions, interval, lapses = card.repetitions, card.interval_days, card.lapses
    if quality < 3:
        repetitions, interval, lapses = 0, 1, lapses + 1
    else:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval * card.ease_factor)
        repetitions += 1
    ease = max(MIN_EASE, card.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    return replace(
        card,
        repetitions=repetitions,
        ease_factor=round(ease, 4),
        interval_days=interval,
        due_date=now.date() + timedelta(days=interval),
        last_reviewed_at=now,
        lapses=lapses,
        review_count=card.review_count + 1,
    )


def is_due(card: VocabularyCard, today: date) -> bool:
    return card.due_date is None or card.due_date <= today
