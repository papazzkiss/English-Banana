"""Grammar (Phase 3) and listening (Phase 6) attempts: assess -> record -> mastery -> next."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from banana_english.application.services.grammar_assessment import LLMGrammarAssessmentEngine
from banana_english.application.services.listening_assessment import ListeningAssessmentEngine
from banana_english.application.use_cases.common import (
    AssessmentFailedError,
    AttemptOutcome,
    NotFoundError,
    UowFactory,
    record_mastery,
    require_learner,
)
from banana_english.application.use_cases.recommendations import GetRecommendations
from banana_english.domain.interfaces.assessment import AssessmentUnavailableError
from banana_english.domain.interfaces.infra import Clock
from banana_english.domain.interfaces.repositories import ContentRepository
from banana_english.domain.models import (
    Assessment,
    Attempt,
    AttemptStatus,
    Exercise,
    ListeningLesson,
    ListeningQuestion,
    Module,
)
from banana_english.domain.models.skills import LISTENING_SKILL


class AttemptRecorder:
    """Assess OUTSIDE the DB transaction (an LLM call can take seconds), then commit attempt +
    mistakes + mastery + mastery event in one short transaction."""

    def __init__(
        self, uow_factory: UowFactory, clock: Clock, recommendations: GetRecommendations
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._recommendations = recommendations

    def run(
        self,
        *,
        learner_id: str,
        module: Module,
        item_id: str,
        skill_id: str,
        answer: str,
        response_time_ms: int | None,
        assess: Callable[[], Assessment],
        extra: dict | None = None,
    ) -> AttemptOutcome:
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            history = uow.attempts.item_history(learner_id).get(item_id)
        attempt_id = str(uuid.uuid4())
        submitted_at: datetime = self._clock.now()
        try:
            assessment = assess()
        except AssessmentUnavailableError as exc:
            with self._uow_factory() as uow:
                uow.attempts.add(
                    Attempt(
                        attempt_id,
                        learner_id,
                        module,
                        item_id,
                        skill_id,
                        answer,
                        submitted_at,
                        AttemptStatus.ASSESSMENT_FAILED,
                        response_time_ms,
                        None,
                        {"error": exc.reason[:500]},
                    )
                )
                uow.commit()
            raise AssessmentFailedError(attempt_id, exc.reason) from exc

        with self._uow_factory() as uow:
            uow.attempts.add(
                Attempt(
                    attempt_id,
                    learner_id,
                    module,
                    item_id,
                    skill_id,
                    answer,
                    submitted_at,
                    AttemptStatus.ASSESSED,
                    response_time_ms,
                    assessment,
                    extra or {},
                )
            )
            change = record_mastery(
                uow,
                learner_id,
                skill_id,
                score=assessment.score,
                is_correct=assessment.is_correct,
                at=submitted_at,
                attempt_id=attempt_id,
                repeat=bool(history and history.ever_correct),
            )
            uow.commit()
        return AttemptOutcome(
            attempt_id,
            item_id,
            skill_id,
            submitted_at,
            assessment,
            [change],
            self._recommendations.first(learner_id),
            extra or {},
        )


class SubmitGrammarAttempt:
    def __init__(
        self,
        recorder: AttemptRecorder,
        content: ContentRepository,
        engine: LLMGrammarAssessmentEngine,
    ) -> None:
        self._recorder = recorder
        self._content = content
        self._engine = engine

    def exercise(self, exercise_id: str) -> Exercise:
        exercise = self._content.get_exercise(exercise_id)
        if exercise is None or exercise.module is not Module.GRAMMAR:
            raise NotFoundError(f"exercise {exercise_id}")
        return exercise

    def execute(
        self, learner_id: str, exercise_id: str, answer: str, response_time_ms: int | None = None
    ) -> AttemptOutcome:
        exercise = self.exercise(exercise_id)
        outcome = self._recorder.run(
            learner_id=learner_id,
            module=Module.GRAMMAR,
            item_id=exercise.id,
            skill_id=exercise.skill_id,
            answer=answer,
            response_time_ms=response_time_ms,
            assess=lambda: self._engine.assess(exercise, answer),
        )
        return AttemptOutcome(**{**outcome.__dict__, "extra": {"exercise": exercise}})


class SubmitListeningAttempt:
    def __init__(
        self,
        recorder: AttemptRecorder,
        content: ContentRepository,
        engine: ListeningAssessmentEngine,
    ) -> None:
        self._recorder = recorder
        self._content = content
        self._engine = engine

    def question(self, question_id: str) -> tuple[ListeningLesson, ListeningQuestion]:
        found = self._content.get_listening_question(question_id)
        if found is None:
            raise NotFoundError(f"question {question_id}")
        return found

    def execute(
        self, learner_id: str, question_id: str, answer: str, response_time_ms: int | None = None
    ) -> AttemptOutcome:
        lesson, question = self.question(question_id)
        outcome = self._recorder.run(
            learner_id=learner_id,
            module=Module.LISTENING,
            item_id=question.id,
            skill_id=LISTENING_SKILL,
            answer=answer,
            response_time_ms=response_time_ms,
            assess=lambda: self._engine.assess(lesson, question, answer),
            extra={"lesson_id": lesson.id},
        )
        return AttemptOutcome(
            **{**outcome.__dict__, "extra": {"lesson": lesson, "question": question}}
        )
