"""Phase 9: explain a stored error on demand."""

from __future__ import annotations

from banana_english.application.services.tutor import Explanation, Tutor
from banana_english.application.use_cases.common import (
    AssessmentFailedError,
    InvalidInputError,
    NotFoundError,
    UowFactory,
    require_learner,
)
from banana_english.domain.interfaces.assessment import AssessmentUnavailableError
from banana_english.domain.interfaces.repositories import ContentRepository
from banana_english.domain.models import Module


class ExplainMistake:
    def __init__(self, uow_factory: UowFactory, tutor: Tutor, content: ContentRepository) -> None:
        self._uow_factory = uow_factory
        self._tutor = tutor
        self._content = content

    def execute(self, learner_id: str, attempt_id: str, mistake_index: int = 0) -> Explanation:
        with self._uow_factory() as uow:
            _, profile = require_learner(uow, learner_id)
            attempt = uow.attempts.get(attempt_id)
        if attempt is None or attempt.learner_id != learner_id:
            raise NotFoundError(f"attempt {attempt_id}")
        if attempt.assessment is None or not attempt.assessment.mistakes:
            raise InvalidInputError("this attempt has no recorded errors to explain")
        if not 0 <= mistake_index < len(attempt.assessment.mistakes):
            raise InvalidInputError("mistake_index out of range")
        mistake = attempt.assessment.mistakes[mistake_index]
        exercise = (
            self._content.get_exercise(attempt.item_id)
            if attempt.module is Module.GRAMMAR
            else None
        )
        try:
            return self._tutor.explain(
                mistake,
                attempt.answer,
                (exercise.accepted_answers[0] if exercise else None)
                or attempt.assessment.corrected_answer,
                profile.current_level.value,
                teacher_rule=exercise.explanation if exercise else None,
                task=f"{exercise.instruction} {exercise.prompt}" if exercise else None,
            )
        except AssessmentUnavailableError as exc:
            raise AssessmentFailedError(None, exc.reason) from exc
