"""Background job bookkeeping (queued -> running -> succeeded | failed)."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from banana_english.application.use_cases.common import (
    AssessmentFailedError,
    MasteryChange,
    NotFoundError,
    UowFactory,
    require_learner,
)
from banana_english.domain.interfaces.infra import Clock, JobRunner
from banana_english.domain.models import Assessment, Job, JobStatus

logger = logging.getLogger("banana_english.jobs")


class JobStore:
    def __init__(self, uow_factory: UowFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def create(self, learner_id: str, kind: str) -> Job:
        now = self._clock.now()
        job = Job(str(uuid.uuid4()), learner_id, kind, JobStatus.QUEUED, now, now)
        with self._uow_factory() as uow:
            uow.jobs.add(job)
            uow.commit()
        return job

    def update(
        self,
        job_id: str,
        status: JobStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._uow_factory() as uow:
            job = uow.jobs.get(job_id)
            if job is None:
                return
            uow.jobs.save(
                replace(
                    job, status=status, result=result, error=error, updated_at=self._clock.now()
                )
            )
            uow.commit()

    def guarded(self, job_id: str, fn: Callable[[], None]) -> Callable[[], None]:
        """Wrap background work so an unexpected crash marks the job failed, never 'running'."""

        def run() -> None:
            try:
                fn()
            except Exception as exc:
                logger.exception("job %s crashed", job_id)
                self.update(job_id, JobStatus.FAILED, error=f"internal error: {type(exc).__name__}")

        return run

    def get(self, learner_id: str, job_id: str) -> Job:
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            job = uow.jobs.get(job_id)
        if job is None or job.learner_id != learner_id:
            raise NotFoundError(f"job {job_id}")
        return job


class BackgroundAttempts:
    """Grade an attempt in a background job; the client polls GET /jobs/{id}.

    LLM grading can outlast what a proxy lets a request stay open, and a request that times out
    after the attempt was recorded invites a retry that would count twice. So a repeat of the
    same submission while the first is still being graded returns the first job. The in-flight
    map lives in this process, like the job runner itself (single-host scope)."""

    def __init__(self, jobs: JobStore, runner: JobRunner) -> None:
        self._jobs = jobs
        self._runner = runner
        self._lock = threading.Lock()
        self._in_flight: dict[tuple[str, str], str] = {}

    def submit(
        self, learner_id: str, kind: str, dedupe_key: str, work: Callable[[], dict[str, Any]]
    ) -> Job:
        key = (learner_id, f"{kind}:{dedupe_key}")
        with self._lock:
            if (job_id := self._in_flight.get(key)) is not None:
                return self._jobs.get(learner_id, job_id)
            job = self._jobs.create(learner_id, kind)
            self._in_flight[key] = job.id

        def run() -> None:
            try:
                self._jobs.update(job.id, JobStatus.RUNNING)
                try:
                    result = work()
                except AssessmentFailedError as exc:
                    self._jobs.update(
                        job.id,
                        JobStatus.FAILED,
                        result={"attempt_id": exc.attempt_id},
                        error=f"Assessment unavailable: {exc}",
                    )
                    return
                self._jobs.update(job.id, JobStatus.SUCCEEDED, result=result)
            finally:
                with self._lock:
                    self._in_flight.pop(key, None)

        self._runner.submit(self._jobs.guarded(job.id, run))
        return job


def assessment_dict(a: Assessment) -> dict[str, Any]:
    return {
        "score": a.score,
        "is_correct": a.is_correct,
        "feedback": a.feedback,
        "assessor": a.assessor.value,
        "mistakes": [
            {
                "category": m.category.value,
                "explanation": m.explanation,
                "fragment": m.fragment,
                "correction": m.correction,
            }
            for m in a.mistakes
        ],
        "corrected_answer": a.corrected_answer,
        "prompt_version": a.prompt_version,
        "model": a.model,
    }


def change_dict(c: MasteryChange) -> dict[str, Any]:
    return {
        "skill_id": c.skill_id,
        "before": round(c.before.mastery, 2),
        "after": round(c.after.mastery, 2),
        "attempt_count": c.after.attempt_count,
    }
