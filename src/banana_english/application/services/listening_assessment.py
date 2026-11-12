"""Listening comprehension (Phase 6). The LLM never "hears" audio: it compares the learner's
free-text answer with the known correct answers + the transcript the audio was made from."""

from __future__ import annotations

from dataclasses import replace

from banana_english.application.services.llm_contracts import ListeningVerdict
from banana_english.application.services.prompts import (
    LISTENING_ASSESSMENT_SYSTEM,
    LISTENING_ASSESSMENT_VERSION,
    render_listening_user,
)
from banana_english.application.services.structured_llm import StructuredLLM, cache_key
from banana_english.domain.interfaces.llm import LLMMessage, LLMRequest
from banana_english.domain.models import (
    Assessment,
    Assessor,
    ListeningLesson,
    ListeningQuestion,
    Mistake,
    MistakeCategory,
)
from banana_english.domain.services.answer_matching import matches_any, normalize_answer

TASK = "listening_assessment"


class ListeningAssessmentEngine:
    def __init__(self, llm: StructuredLLM) -> None:
        self._llm = llm

    def assess(
        self, lesson: ListeningLesson, question: ListeningQuestion, answer: str
    ) -> Assessment:
        normalized = normalize_answer(answer)
        if not normalized:
            return Assessment(
                score=0.0,
                is_correct=False,
                feedback="No answer given.",
                assessor=Assessor.DETERMINISTIC,
                mistakes=(Mistake(MistakeCategory.NO_ANSWER, "The answer was empty."),),
                corrected_answer=question.accepted_answers[0],
            )
        if matches_any(answer, question.accepted_answers):
            return Assessment(
                score=100.0, is_correct=True, feedback="Correct!", assessor=Assessor.REFERENCE_MATCH
            )
        request = LLMRequest(
            task=TASK,
            prompt_version=LISTENING_ASSESSMENT_VERSION,
            messages=(
                LLMMessage("system", LISTENING_ASSESSMENT_SYSTEM),
                LLMMessage("user", render_listening_user(lesson, question, answer)),
            ),
            response_schema=ListeningVerdict.model_json_schema(),
            context={
                "item_id": question.id,
                "accepted_answers": list(question.accepted_answers),
                "learner_answer": answer,
            },
        )
        key = cache_key(
            TASK,
            LISTENING_ASSESSMENT_VERSION,
            self._llm.llm.name,
            LISTENING_ASSESSMENT_SYSTEM,
            render_listening_user(lesson, question, normalized),
        )
        verdict, model = self._llm.run(request, ListeningVerdict, key)
        assessment = verdict.to_assessment(LISTENING_ASSESSMENT_VERSION, model)
        # Learner-facing text from reviewed content (LLM feedback talked about "the learner").
        answer_text = question.accepted_answers[0]
        feedback = {
            "fully": f"Right! ({answer_text})",
            "partly": f"Partly right. The full answer: {answer_text}.",
            "not": f"Not quite. The answer is: {answer_text}. Listen again for this detail.",
        }[verdict.understood]
        return replace(
            assessment,
            feedback=feedback,
            corrected_answer=None if assessment.is_correct else answer_text,
            mistakes=tuple(replace(m, explanation=feedback) for m in assessment.mistakes),
        )
