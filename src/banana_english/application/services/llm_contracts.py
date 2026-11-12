"""Schemas + strict parser for every structured LLM output.

Raw LLM text never reaches the domain. It must pass, in order:
  1. JSON syntax (optionally inside one ```json fence; qwen3 <think> blocks are stripped)
  2. Schema validation (types, enums, lengths, allowed tags, no extra keys)
  3. Grounding: every error fragment must be copied from the learner's answer (catches the
     model grading the exercise sentence instead of the answer — seen in calibration v3)
Only then is it converted into a domain object. Scores are computed deterministically from
the model's categorical judgements (domain/services/rubric.py), never taken as raw numbers.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from banana_english.domain.models import (
    GRAMMAR_MISTAKE_CATEGORIES,
    Assessment,
    Assessor,
    Mistake,
    MistakeCategory,
)
from banana_english.domain.services.answer_matching import normalize_answer
from banana_english.domain.services.rubric import (
    COMPREHENSION_SCORES,
    CORRECT_THRESHOLD,
    score_from_findings,
    severity_for,
)

_FENCE = re.compile(r"^```(?:json)?\s*\n(?P<body>.*)\n```$", re.DOTALL)
_THINK = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)


class InvalidLLMOutputError(Exception):
    pass


def strip_reasoning(raw: str) -> str:
    return _THINK.sub("", raw).strip()


def parse_llm_json[M: BaseModel](
    raw: str, model: type[M], context: dict[str, Any] | None = None
) -> M:
    text = strip_reasoning(raw)
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group("body").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidLLMOutputError(f"not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise InvalidLLMOutputError("top-level JSON value must be an object")
    try:
        return model.model_validate(payload, context=context)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors()
        )
        raise InvalidLLMOutputError(f"schema validation failed: {problems}") from exc


# --- grammar ---------------------------------------------------------------------------


class GrammarError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fragment: str = Field(
        min_length=1, max_length=200, description="Words copied exactly from the learner answer"
    )
    tag: MistakeCategory
    correction: str | None = Field(default=None, max_length=200)
    explanation: str = Field(min_length=1, max_length=400)

    @field_validator("tag")
    @classmethod
    def _grammar_tag(cls, value: MistakeCategory) -> MistakeCategory:
        if value not in GRAMMAR_MISTAKE_CATEGORIES:
            raise ValueError(f"tag '{value}' is not a grammar error tag")
        return value

    @field_validator("fragment")
    @classmethod
    def _grounded(cls, value: str, info: ValidationInfo) -> str:
        answer = (info.context or {}).get("answer")
        if answer is not None and normalize_answer(value) not in normalize_answer(answer):
            raise ValueError("fragment is not part of the learner answer")
        return value


class GrammarVerdict(BaseModel):
    """The exact JSON object the grammar prompt must return (field order = reasoning order)."""

    model_config = ConfigDict(extra="forbid")

    errors: list[GrammarError] = Field(max_length=5)
    natural: bool = Field(description="True if the answer sounds natural to a native speaker")
    corrected_answer: str | None = Field(default=None, max_length=400)
    feedback: str = Field(min_length=1, max_length=600)

    @property
    def score(self) -> int:
        return score_from_findings([severity_for(e.tag.value) for e in self.errors], self.natural)

    def to_assessment(self, prompt_version: str, model: str) -> Assessment:
        score = self.score
        return Assessment(
            score=float(score),
            is_correct=score >= CORRECT_THRESHOLD,
            feedback=self.feedback.strip(),
            assessor=Assessor.LLM,
            mistakes=tuple(
                Mistake(e.tag, e.explanation, fragment=e.fragment, correction=e.correction)
                for e in self.errors
            ),
            corrected_answer=self.corrected_answer if self.errors else None,
            prompt_version=prompt_version,
            model=model,
        )


# --- listening -------------------------------------------------------------------------


class ListeningVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    understood: Literal["fully", "partly", "not"]
    feedback: str = Field(min_length=1, max_length=400)

    def to_assessment(self, prompt_version: str, model: str) -> Assessment:
        score = COMPREHENSION_SCORES[self.understood]
        correct = score >= CORRECT_THRESHOLD
        return Assessment(
            score=float(score),
            is_correct=correct,
            feedback=self.feedback.strip(),
            assessor=Assessor.LLM,
            mistakes=()
            if correct
            else (Mistake(MistakeCategory.COMPREHENSION, self.feedback.strip()),),
            prompt_version=prompt_version,
            model=model,
        )


# --- tutor -----------------------------------------------------------------------------


class TutorExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(min_length=20, max_length=800)
    example: str = Field(min_length=3, max_length=300)

    @model_validator(mode="after")
    def _example_is_new(self, info: ValidationInfo) -> TutorExplanation:
        answer = (info.context or {}).get("answer")
        if answer and normalize_answer(self.example) == normalize_answer(answer):
            raise ValueError("example must be a new sentence, not the learner's answer")
        return self
