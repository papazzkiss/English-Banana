"""Learning roadmap: CEFR milestones (A1 -> A2 -> ...), what each needs, and a time estimate.

A level is reached when every skill introduced at it is mastered (effective mastery >= 80)
and every word of its CEFR word list has been started. The estimate counts the answers still
needed and divides by the daily goal:

* each word not started yet: one answer (its first review; later reviews come on top);
* each skill below 80: the answers that move the mastery EMA (alpha 0.3) from its current
  value to 80, assuming good answers (score 90): from the starting 50 that is 4 answers.

It is a lower bound for a learner who keeps to the daily goal, not a promise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from banana_english.domain.models import CefrLevel, Module

MASTERED_AT = 80.0  # "mastered" everywhere in the app (Progress, dashboard)
DAILY_GOAL = 10  # answers per day, the dashboard's daily goal
ASSUMED_SCORE = 90.0  # a "good" answer on the shared rubric
_ALPHA = 0.3  # MasteryParams.alpha


def answers_to_master(mastery: float) -> int:
    """Good answers needed to move the EMA from `mastery` to MASTERED_AT."""
    if mastery >= MASTERED_AT:
        return 0
    ratio = (ASSUMED_SCORE - MASTERED_AT) / (ASSUMED_SCORE - mastery)
    return max(1, math.ceil(math.log(ratio) / math.log(1 - _ALPHA)))


@dataclass(frozen=True)
class SkillProgress:
    skill_id: str
    name: str
    module: Module
    effective_mastery: float
    attempt_count: int

    @property
    def status(self) -> str:
        if self.effective_mastery >= MASTERED_AT and self.attempt_count:
            return "mastered"
        return "in_progress" if self.attempt_count else "not_started"


@dataclass(frozen=True)
class LevelMilestone:
    level: CefrLevel
    skills: tuple[SkillProgress, ...]
    words_total: int
    words_started: int

    @property
    def skills_mastered(self) -> int:
        return sum(1 for s in self.skills if s.status == "mastered")

    @property
    def answers_left(self) -> int:
        skills = sum(
            answers_to_master(s.effective_mastery if s.attempt_count else 50.0) for s in self.skills
        )
        return skills + (self.words_total - self.words_started)

    @property
    def weeks_left(self) -> int:
        return math.ceil(self.answers_left / (DAILY_GOAL * 7))

    @property
    def complete(self) -> bool:
        return self.answers_left == 0


def roadmap_levels(current: CefrLevel, target: CefrLevel) -> list[CefrLevel]:
    """A1 up to the target (at least one level above the current one)."""
    last = max(target.rank, min(current.rank + 1, len(CefrLevel) - 1))
    return [lvl for lvl in CefrLevel if lvl.rank <= last]
