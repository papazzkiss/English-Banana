"""Grammar assessment (Phase 3): reference match first, rubric-prompted LLM second.

    answer --(empty)---------------------------------> deterministic 0
           --(matches a reviewed reference answer)---> reference_match 100 (no LLM call)
           --> StructuredLLM(grammar prompt)        -> GrammarVerdict (strict) -> rubric score
               invalid twice / provider down         -> AssessmentUnavailableError

Also used for speaking transcripts and conversation turns (grammar_topic="spoken_response").
"""

from __future__ import annotations

import difflib
from dataclasses import replace

from banana_english.application.services.llm_contracts import GrammarVerdict
from banana_english.application.services.prompts import (
    GRAMMAR_ASSESSMENT_SYSTEM,
    GRAMMAR_ASSESSMENT_VERSION,
    render_grammar_user,
)
from banana_english.application.services.structured_llm import StructuredLLM, cache_key
from banana_english.domain.interfaces.assessment import AssessmentEngine
from banana_english.domain.interfaces.llm import LLMMessage, LLMRequest
from banana_english.domain.models import (
    Assessment,
    Assessor,
    Exercise,
    Mistake,
    MistakeCategory,
)
from banana_english.domain.services.answer_matching import matches_any, normalize_answer

TASK = "grammar_assessment"


class LLMGrammarAssessmentEngine(AssessmentEngine):
    def __init__(self, llm: StructuredLLM) -> None:
        self._llm = llm

    def build_request(
        self, exercise: Exercise, answer: str, grammar_topic: str | None = None
    ) -> LLMRequest:
        return LLMRequest(
            task=TASK,
            prompt_version=GRAMMAR_ASSESSMENT_VERSION,
            messages=(
                LLMMessage("system", GRAMMAR_ASSESSMENT_SYSTEM),
                LLMMessage("user", render_grammar_user(exercise, answer, grammar_topic)),
            ),
            response_schema=GrammarVerdict.model_json_schema(),
            temperature=0.0,
            think=True,  # error analysis: find and quote each mistake before the verdict
            context={
                "item_id": exercise.id,
                "skill_id": exercise.skill_id,
                "accepted_answers": list(exercise.accepted_answers),
                "learner_answer": answer,
            },
        )

    def assess(
        self, exercise: Exercise, answer: str, grammar_topic: str | None = None
    ) -> Assessment:
        normalized = normalize_answer(answer)
        if not normalized:
            return Assessment(
                score=0.0,
                is_correct=False,
                feedback="No answer given.",
                assessor=Assessor.DETERMINISTIC,
                mistakes=(Mistake(MistakeCategory.INCOMPLETE_ANSWER, "The answer was empty."),),
                corrected_answer=exercise.accepted_answers[0]
                if exercise.accepted_answers
                else None,
            )
        if exercise.accepted_answers and matches_any(answer, exercise.accepted_answers):
            return Assessment(
                score=100.0, is_correct=True, feedback="Correct!", assessor=Assessor.REFERENCE_MATCH
            )

        request = self.build_request(exercise, answer, grammar_topic)
        # The key covers EVERYTHING the model sees (system prompt + rendered exercise context),
        # with the answer normalised — so any context change (e.g. a new grading hint) can
        # never be answered from a stale verdict.
        key = cache_key(
            TASK,
            GRAMMAR_ASSESSMENT_VERSION,
            self._llm.llm.name,
            GRAMMAR_ASSESSMENT_SYSTEM,
            render_grammar_user(exercise, normalized, grammar_topic),
        )
        verdict, model = self._llm.run(request, GrammarVerdict, key, context={"answer": answer})
        assessment = verdict.to_assessment(GRAMMAR_ASSESSMENT_VERSION, model)
        if exercise.accepted_answers:
            return ground_in_references(
                assessment, answer, exercise.accepted_answers, natural=verdict.natural
            )
        return assessment


def closest_reference(answer: str, references: tuple[str, ...]) -> str:
    norm = normalize_answer(answer)
    return max(
        references, key=lambda r: difflib.SequenceMatcher(None, norm, normalize_answer(r)).ratio()
    )


def ground_in_references(
    assessment: Assessment, answer: str, references: tuple[str, ...], *, natural: bool
) -> Assessment:
    """For reviewed exercises, learner-facing text comes from reviewed content, not the LLM.

    Live check: the LLM scored "I have saw that film yesterday" correctly (major error) but its
    feedback said "use 'have seen'" — wrong advice. The score and the grounded error fragments
    are kept; free-text corrections are kept only if they appear in a reviewed answer, and the
    feedback names the closest reviewed answer instead.
    """
    best = closest_reference(answer, references)
    refs = [normalize_answer(r) for r in references]
    mistakes = tuple(
        m
        if m.correction and any(normalize_answer(m.correction) in r for r in refs)
        else replace(m, correction=None)
        for m in assessment.mistakes
    )
    if assessment.is_correct:
        feedback = (
            "Correct!"
            if natural
            else (f"Correct, but it sounds a little unnatural. A more natural answer: “{best}”")
        )
        corrected = None
    else:
        quoted = ", ".join(f"“{m.fragment}”" for m in mistakes if m.fragment)
        feedback = (
            f"Check {quoted}. " if quoted else "Not quite. "
        ) + f"A correct answer: “{best}”"
        corrected = best
    return replace(assessment, feedback=feedback, mistakes=mistakes, corrected_answer=corrected)
