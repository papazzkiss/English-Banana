"""Phase 8: scenario role-play. The partner never corrects mid-conversation; after the last
turn every learner line is graded in a batch (background job) and errors are summarised."""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import replace

from banana_english.application.services.conversation import ConversationPartner
from banana_english.application.services.grammar_assessment import LLMGrammarAssessmentEngine
from banana_english.application.use_cases.common import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    ProviderUnavailableError,
    UowFactory,
    grammar_skills_for,
    record_mastery,
    require_learner,
)
from banana_english.application.use_cases.jobs import JobStore, assessment_dict, change_dict
from banana_english.domain.interfaces.assessment import AssessmentUnavailableError
from banana_english.domain.interfaces.infra import Clock, JobRunner
from banana_english.domain.interfaces.llm import LLMProviderError
from banana_english.domain.interfaces.repositories import ContentRepository
from banana_english.domain.models import (
    Attempt,
    AttemptStatus,
    ContentReviewStatus,
    Conversation,
    ConversationScenario,
    ConversationStatus,
    ConversationTurn,
    Exercise,
    ExerciseType,
    Job,
    JobStatus,
    Module,
)
from banana_english.domain.models.skills import CONVERSATION_SKILL

MAX_MESSAGE_CHARS = 300


def turn_exercise(scenario: ConversationScenario, previous_line: str) -> Exercise:
    return Exercise(
        id=f"{scenario.id}.turn",
        module=Module.CONVERSATION,
        skill_id=CONVERSATION_SKILL,
        cefr_level=scenario.cefr_level,
        exercise_type=ExerciseType.CONVERSATION_TURN,
        instruction=(
            f"Role-play: {scenario.situation} The learner plays {scenario.learner_role} "
            "and replies to the line below. Grade the learner's reply."
        ),
        prompt=previous_line,
        accepted_answers=(),
        review_status=ContentReviewStatus.APPROVED,
    )


class ConversationPractice:
    def __init__(
        self,
        uow_factory: UowFactory,
        content: ContentRepository,
        partner: ConversationPartner,
        grader: LLMGrammarAssessmentEngine,
        jobs: JobStore,
        runner: JobRunner,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._content = content
        self._partner = partner
        self._grader = grader
        self._jobs = jobs
        self._runner = runner
        self._clock = clock

    def _load(self, uow, learner_id: str, conversation_id: str) -> Conversation:
        require_learner(uow, learner_id)
        conversation = uow.conversations.get(conversation_id)
        if conversation is None or conversation.learner_id != learner_id:
            raise NotFoundError(f"conversation {conversation_id}")
        return conversation

    def scenario_for(self, conversation: Conversation) -> ConversationScenario:
        scenario = self._content.get_scenario(conversation.scenario_id)
        if scenario is None:
            raise NotFoundError(f"scenario {conversation.scenario_id}")
        return scenario

    def start(self, learner_id: str, scenario_id: str) -> Conversation:
        scenario = self._content.get_scenario(scenario_id)
        if scenario is None:
            raise NotFoundError(f"scenario {scenario_id}")
        now = self._clock.now()
        conversation = Conversation(
            str(uuid.uuid4()),
            learner_id,
            scenario.id,
            ConversationStatus.ACTIVE,
            (ConversationTurn("assistant", scenario.opening_line, now),),
            now,
        )
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            uow.conversations.add(conversation)
            uow.commit()
        return conversation

    def get(self, learner_id: str, conversation_id: str) -> Conversation:
        with self._uow_factory() as uow:
            return self._load(uow, learner_id, conversation_id)

    def send(self, learner_id: str, conversation_id: str, text: str) -> Conversation:
        text = " ".join(text.split())
        if not text:
            raise InvalidInputError("message is empty")
        if len(text) > MAX_MESSAGE_CHARS:
            raise InvalidInputError("message is too long")
        with self._uow_factory() as uow:
            conversation = self._load(uow, learner_id, conversation_id)
        scenario = self.scenario_for(conversation)
        if conversation.status is not ConversationStatus.ACTIVE:
            raise ConflictError("conversation is not active")
        if len(conversation.learner_turns) >= scenario.max_learner_turns:
            raise ConflictError("all turns used — finish the conversation to get feedback")
        turns = [*conversation.turns, ConversationTurn("learner", text, self._clock.now())]
        try:
            reply = self._partner.reply(scenario, turns)  # outside the transaction
        except LLMProviderError as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        turns.append(ConversationTurn("assistant", reply, self._clock.now()))
        updated = replace(conversation, turns=tuple(turns))
        with self._uow_factory() as uow:
            uow.conversations.save(updated)
            uow.commit()
        return updated

    def finish(self, learner_id: str, conversation_id: str) -> Job:
        with self._uow_factory() as uow:
            conversation = self._load(uow, learner_id, conversation_id)
            if conversation.status is not ConversationStatus.ACTIVE:
                raise ConflictError("conversation already finished")
            if not conversation.learner_turns:
                raise ConflictError("say something first")
            uow.conversations.save(replace(conversation, status=ConversationStatus.FINISHING))
            uow.commit()
        job = self._jobs.create(learner_id, "conversation_summary")
        self._runner.submit(
            self._jobs.guarded(job.id, lambda: self._summarise(job.id, conversation))
        )
        return job

    def _summarise(self, job_id: str, conversation: Conversation) -> None:
        self._jobs.update(job_id, JobStatus.RUNNING)
        scenario = self.scenario_for(conversation)
        graded = []
        previous = scenario.opening_line
        for turn in conversation.turns:
            if turn.role == "assistant":
                previous = turn.text
                continue
            try:
                assessment = self._grader.assess(
                    turn_exercise(scenario, previous), turn.text, grammar_topic="conversation_turn"
                )
            except AssessmentUnavailableError:
                assessment = None
            graded.append((turn, assessment))

        now = self._clock.now()
        rows, changes, tags = [], [], Counter()
        with self._uow_factory() as uow:
            for index, (turn, assessment) in enumerate(graded):
                attempt_id = str(uuid.uuid4())
                details = {"conversation_id": conversation.id, "turn_index": index}
                if assessment is None:
                    uow.attempts.add(
                        Attempt(
                            attempt_id,
                            conversation.learner_id,
                            Module.CONVERSATION,
                            scenario.id,
                            CONVERSATION_SKILL,
                            turn.text,
                            now,
                            AttemptStatus.ASSESSMENT_FAILED,
                            None,
                            None,
                            details,
                        )
                    )
                    rows.append({"text": turn.text, "attempt_id": attempt_id, "assessment": None})
                    continue
                uow.attempts.add(
                    Attempt(
                        attempt_id,
                        conversation.learner_id,
                        Module.CONVERSATION,
                        scenario.id,
                        CONVERSATION_SKILL,
                        turn.text,
                        now,
                        AttemptStatus.ASSESSED,
                        None,
                        assessment,
                        details,
                    )
                )
                changes.append(
                    record_mastery(
                        uow,
                        conversation.learner_id,
                        CONVERSATION_SKILL,
                        score=assessment.score,
                        is_correct=assessment.is_correct,
                        at=now,
                        attempt_id=attempt_id,
                        source="conversation",
                    )
                )
                for skill in sorted(
                    grammar_skills_for(assessment.mistakes, scenario.target_skills)
                ):
                    changes.append(
                        record_mastery(
                            uow,
                            conversation.learner_id,
                            skill,
                            score=assessment.score,
                            is_correct=False,
                            at=now,
                            attempt_id=attempt_id,
                            source="conversation",
                        )
                    )
                tags.update(m.category.value for m in assessment.mistakes)
                rows.append(
                    {
                        "text": turn.text,
                        "attempt_id": attempt_id,
                        "assessment": assessment_dict(assessment),
                    }
                )
            scored = [r["assessment"]["score"] for r in rows if r["assessment"]]
            summary = {
                "scenario_id": scenario.id,
                "turns": rows,
                "average_score": round(sum(scored) / len(scored), 1) if scored else None,
                "error_counts": dict(tags.most_common()),
                "ungraded_turns": sum(1 for r in rows if r["assessment"] is None),
                "mastery_changes": [change_dict(c) for c in changes],
            }
            uow.conversations.save(
                replace(conversation, status=ConversationStatus.FINISHED, summary=summary)
            )
            uow.commit()
        self._jobs.update(job_id, JobStatus.SUCCEEDED, result=summary)
