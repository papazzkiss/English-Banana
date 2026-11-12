from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from banana_english.domain.interfaces.infra import JobRunner
from banana_english.infrastructure.observability.context import (
    current_request_id,
    reset_request_id,
    set_request_id,
)

logger = logging.getLogger("banana_english.jobs")


class ThreadPoolJobRunner(JobRunner):
    """In-process background execution. Job state lives in the `jobs` table, so clients poll
    GET /api/v1/jobs/{id}. Single-host scope (Phase 11): one API process, a few workers."""

    def __init__(self, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="banana-job")

    def submit(self, fn: Callable[[], None]) -> None:
        request_id = current_request_id()

        def run() -> None:
            token = set_request_id(request_id)
            try:
                fn()
            except Exception:
                logger.exception("background job crashed")
            finally:
                reset_request_id(token)

        self._pool.submit(run)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)


class InlineJobRunner(JobRunner):
    """Runs the job immediately (tests, scripts)."""

    def submit(self, fn: Callable[[], None]) -> None:
        fn()
