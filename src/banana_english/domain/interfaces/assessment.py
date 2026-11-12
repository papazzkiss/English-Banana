from __future__ import annotations

from abc import ABC, abstractmethod

from banana_english.domain.models import Assessment, Exercise


class AssessmentUnavailableError(Exception):
    """No trustworthy assessment could be produced (e.g. repeated malformed LLM output).

    Callers must NOT update mastery when this is raised.
    """

    def __init__(self, reason: str, attempts: int = 0) -> None:
        super().__init__(reason)
        self.reason = reason
        self.attempts = attempts


class AssessmentEngine(ABC):
    @abstractmethod
    def assess(self, exercise: Exercise, answer: str) -> Assessment:
        """Return a validated Assessment (0-100) or raise AssessmentUnavailableError."""
