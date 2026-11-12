"""Profile, mastery, dashboard, recommendations and job polling (Phases 4, 5, 10)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from banana_english.api import mappers
from banana_english.api.deps import ERRORS, ContainerDep, LearnerId
from banana_english.api.schemas import common as c
from banana_english.api.schemas import modules as m
from banana_english.domain.models.skills import SPEAKING_FLUENCY_SKILL, SPEAKING_GRAMMAR_SKILL
from banana_english.domain.services.mastery import WEAKNESS_THRESHOLD
from banana_english.domain.services.roadmap import DAILY_GOAL, MASTERED_AT

router = APIRouter(prefix="/api/v1")


def profile_view(o) -> m.LearnerProfileResponse:
    return m.LearnerProfileResponse(
        learner_id=o.user.id,
        display_name=o.user.display_name,
        current_level=o.profile.current_level,
        target_level=o.profile.target_level,
        native_language=o.profile.native_language,
        created_at=o.profile.created_at,
        total_attempts=o.total_attempts,
        correct_attempts=o.correct_attempts,
        role=o.user.role,
    )


# The views below are shared with the teacher screens (same shapes for a student's progress).


def mastery_view(c_, learner_id: str) -> m.MasteryResponse:
    return m.MasteryResponse(
        learner_id=learner_id,
        weakness_threshold=WEAKNESS_THRESHOLD,
        skills=[
            m.SkillMasteryView(
                skill_id=v.skill.id,
                module=v.skill.module,
                skill_name=v.skill.name,
                mastery=round(v.mastery.mastery, 2),
                effective_mastery=round(v.effective, 2),
                confidence=round(v.mastery.confidence, 4),
                attempt_count=v.mastery.attempt_count,
                correct_count=v.mastery.correct_count,
                last_practiced_at=v.mastery.last_practiced_at,
                is_weak=v.is_weak,
                entry_level=v.skill.entry_level,
            )
            for v in c_.learner.mastery(learner_id)
        ],
    )


def weak_skills_view(c_, learner_id: str, limit: int) -> m.WeakSkillsResponse:
    rows = []
    for w in c_.learner.weak_skills(learner_id, limit):
        skill = c_.content.get_skill(w.mastery.skill_id)
        rows.append(
            m.WeakSkillView(
                skill_id=w.mastery.skill_id,
                skill_name=skill.name if skill else w.mastery.skill_id,
                module=skill.module if skill else "grammar",
                mastery=round(w.mastery.mastery, 2),
                effective_mastery=round(w.effective, 2),
                attempt_count=w.mastery.attempt_count,
            )
        )
    return m.WeakSkillsResponse(
        learner_id=learner_id, weakness_threshold=WEAKNESS_THRESHOLD, skills=rows
    )


def activity_view(c_, learner_id: str, days: int) -> m.ActivityResponse:
    a = c_.learner.activity(learner_id, days)
    return m.ActivityResponse(
        learner_id=learner_id,
        days=[m.ActivityDay(date=d, attempts=n) for d, n in a.days],
        active_days=a.active_days,
        current_streak=a.current_streak,
    )


def _parts(a) -> list[m.AttemptPart]:
    """A spoken answer is stored as a grammar attempt plus a companion fluency attempt; the
    list shows it once, with both scores."""
    fluency = a.details.get("fluency") if a.skill_id == SPEAKING_GRAMMAR_SKILL else None
    if not a.assessment or not isinstance(fluency, dict) or "score" not in fluency:
        return []
    return [
        m.AttemptPart(skill_id=SPEAKING_GRAMMAR_SKILL, score=a.assessment.score),
        m.AttemptPart(skill_id=SPEAKING_FLUENCY_SKILL, score=float(fluency["score"])),
    ]


def attempts_view(c_, learner_id: str, limit: int) -> list[m.RecentAttemptView]:
    return [
        m.RecentAttemptView(
            attempt_id=a.id,
            module=a.module,
            item_id=a.item_id,
            skill_id=a.skill_id,
            answer=a.answer,
            submitted_at=a.submitted_at,
            status=a.status.value,
            score=a.assessment.score if a.assessment else None,
            is_correct=a.assessment.is_correct if a.assessment else None,
            mistake_count=len(a.assessment.mistakes) if a.assessment else 0,
            parts=_parts(a),
        )
        for a in c_.learner.recent_attempts(learner_id, limit)
    ]


@router.get(
    "/learner/profile", response_model=m.LearnerProfileResponse, responses=ERRORS, tags=["learner"]
)
def getprofile_view(learner_id: LearnerId, c_: ContainerDep):
    return profile_view(c_.learner.profile(learner_id))


@router.get(
    "/learner/mastery",
    response_model=m.MasteryResponse,
    responses=ERRORS,
    tags=["learner"],
    summary="Mastery (0-100) per skill tag, unpractised skills included",
)
def get_mastery(learner_id: LearnerId, c_: ContainerDep):
    return mastery_view(c_, learner_id)


@router.get(
    "/learner/weak-skills",
    response_model=m.WeakSkillsResponse,
    responses=ERRORS,
    tags=["learner"],
    summary="Skills below the weakness threshold (same query as the recommender)",
)
def weak_skills(
    learner_id: LearnerId, c_: ContainerDep, limit: Annotated[int, Query(ge=1, le=20)] = 5
):
    return weak_skills_view(c_, learner_id, limit)


@router.get(
    "/learner/mastery-history",
    response_model=m.MasteryHistoryResponse,
    responses=ERRORS,
    tags=["learner"],
    summary="Mastery after every attempt (snapshot per attempt, not per day)",
)
def mastery_history(
    learner_id: LearnerId,
    c_: ContainerDep,
    skill_id: str | None = None,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
):
    events = c_.learner.mastery_history(learner_id, skill_id, days)
    return m.MasteryHistoryResponse(
        learner_id=learner_id,
        days=days,
        points=[
            m.MasteryPoint(
                at=e.at,
                skill_id=e.skill_id,
                mastery=round(e.mastery_after, 2),
                score=e.score,
                source=e.source,
            )
            for e in events
        ],
    )


@router.get(
    "/learner/activity",
    response_model=m.ActivityResponse,
    responses=ERRORS,
    tags=["learner"],
    summary="Practice days and streak",
)
def activity(learner_id: LearnerId, c_: ContainerDep, days: Annotated[int, Query(ge=1, le=90)] = 7):
    return activity_view(c_, learner_id, days)


@router.get(
    "/learner/attempts",
    response_model=list[m.RecentAttemptView],
    responses=ERRORS,
    tags=["learner"],
    summary="Most recent attempts",
)
def recent_attempts(
    learner_id: LearnerId, c_: ContainerDep, limit: Annotated[int, Query(ge=1, le=100)] = 20
):
    return attempts_view(c_, learner_id, limit)


def roadmap_view(c_, learner_id: str) -> m.RoadmapResponse:
    profile, levels = c_.learner.roadmap(learner_id)
    return m.RoadmapResponse(
        learner_id=learner_id,
        current_level=profile.current_level,
        target_level=profile.target_level,
        daily_goal=DAILY_GOAL,
        mastered_at=MASTERED_AT,
        levels=[
            m.RoadmapLevel(
                level=lv.level,
                skills=[
                    m.RoadmapSkill(
                        skill_id=s.skill_id,
                        skill_name=s.name,
                        module=s.module,
                        effective_mastery=round(s.effective_mastery, 2),
                        status=s.status,
                    )
                    for s in lv.skills
                ],
                skills_mastered=lv.skills_mastered,
                words_total=lv.words_total,
                words_started=lv.words_started,
                answers_left=lv.answers_left,
                weeks_left=lv.weeks_left,
                complete=lv.complete,
            )
            for lv in levels
        ],
    )


@router.get(
    "/learner/roadmap",
    response_model=m.RoadmapResponse,
    responses=ERRORS,
    tags=["learner"],
    summary="CEFR milestones up to the target level, with the skills and words each needs",
)
def get_roadmap(learner_id: LearnerId, c_: ContainerDep):
    return roadmap_view(c_, learner_id)


@router.get(
    "/recommendation/next",
    response_model=c.RecommendationsResponse,
    responses=ERRORS,
    tags=["recommendation"],
    summary="Next activities, weakest skills first",
)
def next_recommendations(
    learner_id: LearnerId, c_: ContainerDep, n: Annotated[int, Query(ge=1, le=10)] = 5
):
    recs, generated_at = c_.recommendations.execute(learner_id, n)
    return c.RecommendationsResponse(
        learner_id=learner_id,
        generated_at=generated_at,
        recommendations=[mappers.recommendation(r) for r in recs],
    )


@router.get(
    "/jobs/{job_id}",
    response_model=c.JobResponse,
    responses=ERRORS,
    tags=["jobs"],
    summary="Poll a background job (speaking assessment, conversation summary)",
)
def get_job(job_id: str, learner_id: LearnerId, c_: ContainerDep):
    return mappers.job(c_.jobs.get(learner_id, job_id))
