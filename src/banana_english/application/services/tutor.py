"""AI Tutor (Phase 9): an explanation layer over errors that assessments already stored.
Called on demand ("why is this wrong?"), never automatically after every attempt."""

from __future__ import annotations

from dataclasses import dataclass

from banana_english.application.services.llm_contracts import TutorExplanation
from banana_english.application.services.prompts import (
    TUTOR_EXPLAIN_VERSION,
    TUTOR_SYSTEM,
    render_tutor_user,
)
from banana_english.application.services.structured_llm import StructuredLLM, cache_key
from banana_english.domain.interfaces.llm import LLMMessage, LLMRequest
from banana_english.domain.models import Mistake

TASK = "tutor_explain"


@dataclass(frozen=True)
class Explanation:
    error_tag: str
    explanation: str
    example: str
    prompt_version: str
    model: str


class Tutor:
    def __init__(self, llm: StructuredLLM) -> None:
        self._llm = llm

    def explain(
        self,
        mistake: Mistake,
        user_answer: str,
        correct_answer: str | None,
        cefr_level: str,
        teacher_rule: str | None = None,
        task: str | None = None,
    ) -> Explanation:
        """teacher_rule: the human-reviewed explanation of the exercise, used as grounding
        (tutor v1 check: 2/10 explanations contradicted the rule without it)."""
        request = LLMRequest(
            task=TASK,
            prompt_version=TUTOR_EXPLAIN_VERSION,
            messages=(
                LLMMessage("system", TUTOR_SYSTEM),
                LLMMessage(
                    "user",
                    render_tutor_user(
                        mistake.category.value,
                        mistake.explanation,
                        user_answer,
                        correct_answer or mistake.correction,
                        cefr_level,
                        teacher_rule,
                        task,
                    ),
                ),
            ),
            response_schema=TutorExplanation.model_json_schema(),
            temperature=0.2,
            think=True,  # a grounded explanation of why the answer is wrong
            context={
                "error_tag": mistake.category.value,
                "learner_answer": user_answer,
                "correct_form": correct_answer or mistake.correction,
            },
        )
        key = cache_key(
            TASK, TUTOR_EXPLAIN_VERSION, self._llm.llm.name, *(m.content for m in request.messages)
        )
        parsed, model = self._llm.run(
            request, TutorExplanation, key, context={"answer": user_answer}
        )
        return Explanation(
            mistake.category.value,
            parsed.explanation.strip(),
            parsed.example.strip(),
            TUTOR_EXPLAIN_VERSION,
            model,
        )
