"""Domain -> HTTP schema mapping (keeps routes thin and the domain framework-free)."""

from __future__ import annotations

from banana_english.api.schemas import common as c
from banana_english.api.schemas import modules as m
from banana_english.application.use_cases.common import AttemptOutcome, MasteryChange
from banana_english.domain.models import (
    Assessment,
    ConversationScenario,
    Exercise,
    Job,
    Recommendation,
    VocabularyCard,
    VocabularyItem,
)
from banana_english.domain.services.rubric import band_for


def assessment(a: Assessment) -> c.AssessmentView:
    return c.AssessmentView(
        score=round(a.score, 1),
        is_correct=a.is_correct,
        band=band_for(a.score).label,
        feedback=a.feedback,
        mistakes=[
            c.MistakeView(
                category=x.category,
                explanation=x.explanation,
                fragment=x.fragment,
                correction=x.correction,
            )
            for x in a.mistakes
        ],
        corrected_answer=a.corrected_answer,
        assessor=a.assessor,
        prompt_version=a.prompt_version,
        model=a.model,
    )


def change(ch: MasteryChange) -> c.MasteryChangeView:
    return c.MasteryChangeView(
        skill_id=ch.skill_id,
        before=round(ch.before.mastery, 2),
        after=round(ch.after.mastery, 2),
        attempt_count=ch.after.attempt_count,
    )


def exercise(e: Exercise) -> c.ExerciseView:
    return c.ExerciseView(
        id=e.id,
        module=e.module,
        skill_id=e.skill_id,
        cefr_level=e.cefr_level,
        difficulty=e.difficulty,
        exercise_type=e.exercise_type,
        instruction=e.instruction,
        prompt=e.prompt,
        hint=e.hint,
    )


def recommendation(r: Recommendation) -> c.RecommendationView:
    return c.RecommendationView(
        priority=r.priority,
        kind=r.kind,
        module=r.module,
        skill_id=r.skill_id,
        reason_code=r.reason_code,
        reason=r.reason,
        evidence=r.evidence,
        items=[
            c.ActivityItemView(
                module=i.module, item_id=i.item_id, title=i.title, difficulty=i.difficulty
            )
            for i in r.items
        ],
    )


def attempt(
    o: AttemptOutcome, reference_answers: list[str], explanation: str | None
) -> c.AttemptResponse:
    return c.AttemptResponse(
        attempt_id=o.attempt_id,
        item_id=o.item_id,
        skill_id=o.skill_id,
        submitted_at=o.submitted_at,
        assessment=assessment(o.assessment),
        reference_answers=reference_answers,
        explanation=explanation,
        mastery_changes=[change(x) for x in o.changes],
        next_recommendation=recommendation(o.next_recommendation)
        if o.next_recommendation
        else None,
    )


def card_back(item: VocabularyItem) -> m.CardBack:
    return m.CardBack(
        word=item.word,
        variants=list(item.variants),
        part_of_speech=item.part_of_speech,
        definition=item.definition,
        example=item.example,
    )


def card_state(card: VocabularyCard) -> m.CardStateView:
    return m.CardStateView(
        repetitions=card.repetitions,
        ease_factor=card.ease_factor,
        interval_days=card.interval_days,
        due_date=card.due_date,
        lapses=card.lapses,
        review_count=card.review_count,
    )


def job(j: Job) -> c.JobResponse:
    return c.JobResponse(
        job_id=j.id,
        kind=j.kind,
        status=j.status.value,
        result=j.result,
        error=j.error,
        created_at=j.created_at,
        updated_at=j.updated_at,
    )


def scenario(s: ConversationScenario) -> m.ScenarioView:
    return m.ScenarioView(
        id=s.id,
        title=s.title,
        cefr_level=s.cefr_level,
        situation=s.situation,
        learner_role=s.learner_role,
        goals=list(s.goals),
        max_learner_turns=s.max_learner_turns,
    )
