"""Shared pieces of every use case: learner lookup, mastery recording, error types."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from banana_english.domain.interfaces.repositories import UnitOfWork
from banana_english.domain.models import (
    Assessment,
    LearnerProfile,
    MasteryEvent,
    Mistake,
    MistakeCategory,
    Principal,
    Recommendation,
    SkillMastery,
    User,
)
from banana_english.domain.services.access import Permission, can
from banana_english.domain.services.mastery import initial_mastery, update_mastery

UowFactory = Callable[[], UnitOfWork]


class UseCaseError(Exception):
    code = "error"


class LearnerNotFoundError(UseCaseError):
    code = "learner_not_found"


class UnauthorizedError(UseCaseError):
    code = "unauthorized"


class ForbiddenError(UseCaseError):
    """Signed in, but this role (or this user) may not do that."""

    code = "forbidden"


class AccountDisabledError(ForbiddenError):
    code = "account_disabled"


class TooManyAttemptsError(UseCaseError):
    code = "too_many_attempts"


class NotFoundError(UseCaseError):
    code = "not_found"


class ConflictError(UseCaseError):
    code = "conflict"


class InvalidInputError(UseCaseError):
    code = "invalid_input"


class AssessmentFailedError(UseCaseError):
    """The attempt was recorded, but no trustworthy assessment exists; mastery untouched."""

    code = "assessment_unavailable"

    def __init__(self, attempt_id: str | None, reason: str) -> None:
        super().__init__(reason)
        self.attempt_id = attempt_id


class ProviderUnavailableError(UseCaseError):
    code = "provider_unavailable"


def require_permission(actor: Principal, permission: Permission) -> None:
    """Defence in depth: the API checks the role too, but a use case never trusts its caller."""
    if not can(actor.role, permission):
        raise ForbiddenError("you do not have access to this")


@dataclass(frozen=True)
class MasteryChange:
    skill_id: str
    before: SkillMastery
    after: SkillMastery


@dataclass(frozen=True)
class AttemptOutcome:
    attempt_id: str
    item_id: str
    skill_id: str
    submitted_at: datetime
    assessment: Assessment
    changes: list[MasteryChange]
    next_recommendation: Recommendation | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def require_learner(uow: UnitOfWork, learner_id: str) -> tuple[User, LearnerProfile]:
    found = uow.learners.get(learner_id)
    if found is None:
        raise LearnerNotFoundError(learner_id)
    return found


def record_mastery(
    uow: UnitOfWork,
    learner_id: str,
    skill_id: str,
    *,
    score: float,
    is_correct: bool,
    at: datetime,
    attempt_id: str | None,
    repeat: bool = False,
    source: str = "attempt",
) -> MasteryChange:
    before = uow.mastery.get(learner_id, skill_id) or initial_mastery(learner_id, skill_id)
    after = update_mastery(
        before, score=score, is_correct=is_correct, practiced_at=at, repeat=repeat
    )
    uow.mastery.save(after)
    uow.mastery.add_event(
        MasteryEvent(
            learner_id, skill_id, score, before.mastery, after.mastery, at, attempt_id, source
        )
    )
    return MasteryChange(skill_id, before, after)


# Error tag -> grammar skill tag, used when free production (speaking, conversation) reveals a
# specific grammar weakness. Tense errors map to the tense skill the task targets.
_CATEGORY_SKILL = {
    MistakeCategory.ARTICLE: "grammar.articles",
    MistakeCategory.PREPOSITION: "grammar.prepositions_time_place",
    MistakeCategory.COMPARATIVE_FORM: "grammar.comparatives_superlatives",
    MistakeCategory.CONDITIONAL_STRUCTURE: "grammar.conditionals",
    MistakeCategory.SUBJECT_VERB_AGREEMENT: "grammar.present_simple_continuous",
}
_TENSE_SKILLS = ("grammar.past_simple_present_perfect", "grammar.present_simple_continuous")


def grammar_skills_for(mistakes: Iterable[Mistake], target_skills: Iterable[str]) -> set[str]:
    targets = list(target_skills)
    skills: set[str] = set()
    for m in mistakes:
        if m.category in _CATEGORY_SKILL:
            skills.add(_CATEGORY_SKILL[m.category])
        elif m.category in (MistakeCategory.VERB_TENSE, MistakeCategory.VERB_FORM):
            tense = next((s for s in targets if s in _TENSE_SKILLS), None)
            if tense:
                skills.add(tense)
    return skills
