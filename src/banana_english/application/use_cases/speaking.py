"""Phase 7: upload audio -> background job (STT + grammar grading + fluency) -> poll result.

The uploaded audio is deleted once transcribed (privacy); the transcript is stored and always
shown to the learner next to the scores.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from banana_english.application.services.speaking_assessment import (
    SpeakingAssessor,
    SpeechTooShortError,
)
from banana_english.application.use_cases.common import (
    InvalidInputError,
    NotFoundError,
    UowFactory,
    grammar_skills_for,
    record_mastery,
    require_learner,
)
from banana_english.application.use_cases.jobs import JobStore, assessment_dict, change_dict
from banana_english.application.use_cases.recommendations import GetRecommendations
from banana_english.domain.interfaces.assessment import AssessmentUnavailableError
from banana_english.domain.interfaces.infra import Clock, JobRunner
from banana_english.domain.interfaces.repositories import ContentRepository
from banana_english.domain.interfaces.stt import STTError
from banana_english.domain.models import Attempt, AttemptStatus, Job, JobStatus, Module
from banana_english.domain.models.skills import SPEAKING_FLUENCY_SKILL, SPEAKING_GRAMMAR_SKILL

logger = logging.getLogger("banana_english.speaking")
ALLOWED_SUFFIXES = {".webm", ".ogg", ".wav", ".mp3", ".m4a", ".mp4", ".oga"}


class SpeakingPractice:
    def __init__(
        self,
        uow_factory: UowFactory,
        content: ContentRepository,
        assessor: SpeakingAssessor,
        jobs: JobStore,
        runner: JobRunner,
        clock: Clock,
        recommendations: GetRecommendations,
        upload_dir: Path,
        max_upload_bytes: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._content = content
        self._assessor = assessor
        self._jobs = jobs
        self._runner = runner
        self._clock = clock
        self._recommendations = recommendations
        self._upload_dir = upload_dir
        self._max_bytes = max_upload_bytes

    def submit(self, learner_id: str, prompt_id: str, audio: bytes, filename: str) -> Job:
        prompt = self._content.get_speaking(prompt_id)
        if prompt is None:
            raise NotFoundError(f"speaking prompt {prompt_id}")
        suffix = Path(filename or "audio.webm").suffix.lower() or ".webm"
        if suffix not in ALLOWED_SUFFIXES:
            raise InvalidInputError(f"unsupported audio type {suffix}")
        if not audio:
            raise InvalidInputError("empty audio upload")
        if len(audio) > self._max_bytes:
            raise InvalidInputError("audio upload too large")
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
        job = self._jobs.create(learner_id, "speaking_assessment")
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        path = self._upload_dir / f"{job.id}{suffix}"
        path.write_bytes(audio)
        self._runner.submit(
            self._jobs.guarded(job.id, lambda: self._run(job.id, learner_id, prompt_id, path))
        )
        return job

    def _run(self, job_id: str, learner_id: str, prompt_id: str, path: Path) -> None:
        self._jobs.update(job_id, JobStatus.RUNNING)
        prompt = self._content.get_speaking(prompt_id)
        try:
            result = self._assessor.assess(prompt, str(path))
        except STTError as exc:
            self._jobs.update(job_id, JobStatus.FAILED, error=f"Could not transcribe audio: {exc}")
            return
        except SpeechTooShortError as exc:
            self._jobs.update(job_id, JobStatus.FAILED, error=str(exc))
            return
        except AssessmentUnavailableError as exc:
            self._jobs.update(job_id, JobStatus.FAILED, error=f"Assessment unavailable: {exc}")
            return
        finally:
            for p in (path, path.with_name(path.name + ".txt")):
                p.unlink(missing_ok=True)

        now = self._clock.now()
        grammar_id, fluency_id = str(uuid.uuid4()), str(uuid.uuid4())
        t = result.transcript
        details = {
            "prompt_id": prompt.id,
            "transcript": t.text,
            "duration_seconds": t.duration_seconds,
            "stt_model": t.model,
            "fluency": result.fluency.__dict__,
        }
        with self._uow_factory() as uow:
            uow.attempts.add(
                Attempt(
                    grammar_id,
                    learner_id,
                    Module.SPEAKING,
                    prompt.id,
                    SPEAKING_GRAMMAR_SKILL,
                    t.text,
                    now,
                    AttemptStatus.ASSESSED,
                    None,
                    result.grammar,
                    details,
                )
            )
            uow.attempts.add(
                Attempt(
                    fluency_id,
                    learner_id,
                    Module.SPEAKING,
                    prompt.id,
                    SPEAKING_FLUENCY_SKILL,
                    t.text,
                    now,
                    AttemptStatus.ASSESSED,
                    None,
                    result.fluency_assessment,
                    details,
                )
            )
            changes = [
                record_mastery(
                    uow,
                    learner_id,
                    SPEAKING_GRAMMAR_SKILL,
                    score=result.grammar.score,
                    is_correct=result.grammar.is_correct,
                    at=now,
                    attempt_id=grammar_id,
                ),
                record_mastery(
                    uow,
                    learner_id,
                    SPEAKING_FLUENCY_SKILL,
                    score=result.fluency.score,
                    is_correct=result.fluency_assessment.is_correct,
                    at=now,
                    attempt_id=fluency_id,
                ),
            ]
            targets = [prompt.target_grammar] if prompt.target_grammar else []
            for skill in sorted(grammar_skills_for(result.grammar.mistakes, targets)):
                changes.append(
                    record_mastery(
                        uow,
                        learner_id,
                        skill,
                        score=result.grammar.score,
                        is_correct=False,
                        at=now,
                        attempt_id=grammar_id,
                        source="speaking",
                    )
                )
            uow.commit()
        self._jobs.update(
            job_id,
            JobStatus.SUCCEEDED,
            result={
                "prompt_id": prompt.id,
                "attempt_id": grammar_id,
                "transcript": t.text,
                "duration_seconds": t.duration_seconds,
                "stt_model": t.model,
                "grammar": assessment_dict(result.grammar),
                "fluency": {
                    **result.fluency.__dict__,
                    "assessment": assessment_dict(result.fluency_assessment),
                },
                "mastery_changes": [change_dict(c) for c in changes],
            },
        )
