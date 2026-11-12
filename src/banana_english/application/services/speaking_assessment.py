"""Speaking (Phase 7): transcribe, then reuse the Phase 3 grammar grader on the transcript,
plus deterministic fluency metrics. The transcript is always returned to the learner, so a
low score can be traced to an STT error instead of being presented as the truth.

Phoneme-level pronunciation scoring is deliberately out of scope (needs forced alignment /
wav2vec2-class models).
"""

from __future__ import annotations

from dataclasses import dataclass

from banana_english.application.services.grammar_assessment import LLMGrammarAssessmentEngine
from banana_english.domain.interfaces.stt import STTProvider, Transcript
from banana_english.domain.models import (
    Assessment,
    Assessor,
    ContentReviewStatus,
    Exercise,
    ExerciseType,
    Mistake,
    MistakeCategory,
    Module,
    SpeakingPrompt,
)
from banana_english.domain.models.skills import SPEAKING_GRAMMAR_SKILL
from banana_english.domain.services.fluency import MIN_WORDS, FluencyMetrics, fluency_metrics
from banana_english.domain.services.rubric import CORRECT_THRESHOLD


class SpeechTooShortError(Exception):
    """Fewer than MIN_WORDS words were heard: too little speech to grade, so nothing is
    scored or stored (a score for "Hello, hello" would only add noise to mastery)."""

    def __init__(self, transcript: Transcript, word_count: int) -> None:
        self.transcript = transcript
        self.word_count = word_count
        heard = transcript.text.strip()
        super().__init__(
            (
                f"We only heard {word_count} word{'' if word_count == 1 else 's'}: “{heard}”. "
                if heard
                else "We could not hear any words. "
            )
            + f"That is too short to grade. Answer the question in at least {MIN_WORDS} "
            "words and try again."
        )


@dataclass(frozen=True)
class SpeakingResult:
    transcript: Transcript
    grammar: Assessment
    fluency: FluencyMetrics
    fluency_assessment: Assessment


_TARGET_HINT = {
    "grammar.past_simple_present_perfect": "past events need past tenses (went, swam, ate)",
    "grammar.present_simple_continuous": "habits and facts need the present simple",
    "grammar.comparatives_superlatives": "comparisons need correct -er/more and than",
    "grammar.conditionals": "if-sentences need correct conditional forms",
    "grammar.prepositions_time_place": "places and times need the right prepositions",
}


def spoken_exercise(prompt: SpeakingPrompt) -> Exercise:
    # Free speech has no reference answer; tell the grader which grammar the task targets,
    # otherwise the lenient "many answers are correct" rule lets tense errors through
    # (live check: "Last weekend I go to the beach" scored 95 without this hint).
    hint = _TARGET_HINT.get(prompt.target_grammar or "")
    return Exercise(
        id=prompt.id,
        module=Module.SPEAKING,
        skill_id=SPEAKING_GRAMMAR_SKILL,
        cefr_level=prompt.cefr_level,
        exercise_type=ExerciseType.SPEAKING_PROMPT,
        instruction="The learner answered this speaking task out loud; this is the transcript.",
        prompt=prompt.instruction,
        accepted_answers=(),
        review_status=ContentReviewStatus.APPROVED,
        difficulty=prompt.difficulty,
        explanation=(
            f"Spoken answer to the task. Check every verb: {hint}. Each wrong form is an error."
            if hint
            else "Spoken answer to the task. Check every verb."
        ),
    )


class SpeakingAssessor:
    def __init__(self, stt: STTProvider, grammar: LLMGrammarAssessmentEngine) -> None:
        self._stt = stt
        self._grammar = grammar

    def assess(self, prompt: SpeakingPrompt, audio_path: str) -> SpeakingResult:
        transcript = self._stt.transcribe(audio_path)
        fluency = fluency_metrics(list(transcript.segments), transcript.text)
        if fluency.word_count < MIN_WORDS:
            raise SpeechTooShortError(transcript, fluency.word_count)
        grammar = self._grammar.assess(
            spoken_exercise(prompt), transcript.text, grammar_topic="spoken_response"
        )
        fluency_assessment = Assessment(
            score=fluency.score,
            is_correct=fluency.score >= CORRECT_THRESHOLD,
            feedback=(
                f"{fluency.words_per_minute:.0f} words per minute, "
                f"{fluency.filler_count} filler words, {fluency.long_pauses} long pauses."
            ),
            assessor=Assessor.DETERMINISTIC,
            mistakes=()
            if fluency.score >= CORRECT_THRESHOLD
            else (
                Mistake(
                    MistakeCategory.FLUENCY, "Speech was too slow, too hesitant, or too short."
                ),
            ),
        )
        return SpeakingResult(transcript, grammar, fluency, fluency_assessment)
