"""Question bank: dynamic practice sets for grammar, vocabulary, reading and listening, and
instant rule-based answer checking (no LLM on the answer path)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from banana_english.api import mappers
from banana_english.api.deps import ERRORS, ContainerDep, LearnerId, Reviewer
from banana_english.api.schemas import admin as ra
from banana_english.api.schemas import bank as b
from banana_english.domain.models import CefrLevel, Module
from banana_english.domain.models.bank import (
    BankPassage,
    BankQuestion,
    BankStatus,
    QuestionFilter,
)

router = APIRouter(prefix="/api/v1/bank", tags=["question-bank"])
SkillPath = Annotated[b.BankSkill, Path(description="grammar, vocabulary, reading or listening")]
AUDIO_PREFIX = "/media/bank/"


def _question(q: BankQuestion) -> b.BankQuestionView:
    left = q.display.get("left")
    return b.BankQuestionView(
        id=q.id,
        qtype=q.qtype,
        level=q.level,
        topic=q.topic,
        point=q.point,
        difficulty=q.difficulty,
        instruction=q.instruction,
        prompt=q.prompt,
        options=[b.BankOptionView(id=o.id, text=o.text) for o in q.options],
        passage_id=q.passage_id,
        pieces=q.display.get("pieces"),
        left=[b.BankOptionView(**x) for x in left] if left else None,
    )


def _passage(p: BankPassage) -> b.BankPassageView:
    listening = p.skill is Module.LISTENING
    return b.BankPassageView(
        id=p.id,
        level=p.level,
        topic=p.topic,
        title=p.title,
        text=None if listening else p.text,
        audio_url=AUDIO_PREFIX + p.audio if p.audio else None,
        duration_s=p.duration_s,
        source=dict(p.source),
    )


@router.get(
    "/{skill}/facets",
    response_model=b.BankFacetsResponse,
    responses=ERRORS,
    summary="What the pool holds, for the set filters (counts per level, topic, point, type)",
)
def facets(skill: SkillPath, learner_id: LearnerId, c_: ContainerDep):
    f = c_.bank.facets(Module(skill))
    names = {k: v.name for k, v in c_.content.bank_points.items()}
    return b.BankFacetsResponse(
        skill=skill,
        total=sum(f["levels"].values()),
        point_names={k: names.get(k, k.replace("_", " ")) for k in f["points"]},
        **f,
    )


@router.post(
    "/{skill}/sets",
    response_model=b.BankSetResponse,
    responses=ERRORS,
    summary="Draw a new practice set from the pool (never the same fixed test)",
)
def new_set(skill: SkillPath, body: b.BankSetRequest, learner_id: LearnerId, c_: ContainerDep):
    f = QuestionFilter(
        skill=Module(skill),
        levels=tuple(body.levels),
        topics=tuple(body.topics),
        points=tuple(body.points),
        qtypes=tuple(body.qtypes),
        difficulties=tuple(body.difficulties),
    )
    s = c_.bank.build_set(learner_id, f, body.count)
    return b.BankSetResponse(
        skill=skill,
        questions=[_question(q) for q in s.questions],
        passages=[_passage(p) for p in s.passages.values()],
        review_count=s.review_count,
    )


@router.post(
    "/answer",
    response_model=b.BankAnswerResponse,
    responses=ERRORS,
    summary="Check one answer instantly; records the attempt, mastery and question history",
)
def answer(body: b.BankAnswerRequest, learner_id: LearnerId, c_: ContainerDep):
    o = c_.bank.answer(learner_id, body.question_id, body.answer, body.response_time_ms)
    return b.BankAnswerResponse(
        attempt_id=o.attempt_id,
        question_id=o.question.id,
        correct=o.result.correct,
        score=o.result.score,
        correct_answer=o.result.correct_answer,
        explanation=o.question.explanation,
        explanation_vi=o.question.explanation_vi,
        detail=dict(o.result.detail),
        mastery=mappers.change(o.mastery),
    )


@router.get(
    "/passages/{passage_id}/transcript",
    response_model=b.BankTranscriptResponse,
    responses=ERRORS,
    summary="Transcript of a listening recording (show it after answering)",
)
def transcript(passage_id: str, learner_id: LearnerId, c_: ContainerDep):
    p = c_.bank.passage_transcript(learner_id, passage_id)
    return b.BankTranscriptResponse(passage_id=p.id, title=p.title, transcript=p.text)


@router.get(
    "/{skill}/summary",
    response_model=b.BankSummaryResponse,
    responses=ERRORS,
    summary="The learner's progress through this skill's pool",
)
def summary(skill: SkillPath, learner_id: LearnerId, c_: ContainerDep):
    return b.BankSummaryResponse(skill=skill, **c_.bank.summary(learner_id, Module(skill)))


# --- review: teachers and admins (403 for students) ------------------------------------------


def _review_view(q: BankQuestion, reviewed_by, reviewed_at) -> ra.ReviewQuestionView:
    return ra.ReviewQuestionView(
        id=q.id,
        skill=q.skill,
        skill_id=q.skill_id,
        level=q.level,
        topic=q.topic,
        point=q.point,
        difficulty=q.difficulty,
        qtype=q.qtype,
        status=q.status,
        quality=q.quality,
        instruction=q.instruction,
        prompt=q.prompt,
        options=[ra.ReviewOptionView(id=o.id, text=o.text) for o in q.options],
        display=dict(q.display),
        answer=dict(q.answer),
        explanation=q.explanation,
        explanation_vi=q.explanation_vi,
        passage_id=q.passage_id,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
    )


@router.get(
    "/{skill}/review",
    response_model=ra.ReviewPageResponse,
    responses=ERRORS,
    summary="Questions of any status, with answers, for review (teachers and admins)",
)
def review_page(
    skill: SkillPath,
    reviewer: Reviewer,
    c_: ContainerDep,
    status: BankStatus | None = None,
    level: CefrLevel | None = None,
    point: Annotated[str | None, Query(max_length=48)] = None,
    q: Annotated[str, Query(max_length=64, description="Question id contains")] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    f = QuestionFilter(
        skill=Module(skill),
        levels=(level,) if level else (),
        points=(point,) if point else (),
        statuses=(status,) if status else tuple(BankStatus),
    )
    rows, total = c_.bank.review_page(reviewer, f, q, limit, offset)
    return ra.ReviewPageResponse(total=total, questions=[_review_view(*r) for r in rows])


@router.patch(
    "/questions/{question_id}",
    response_model=ra.ReviewQuestionView,
    responses=ERRORS,
    summary="Approve, re-validate or disable a question (teachers and admins)",
)
def review_question(
    question_id: str, body: ra.ReviewStatusRequest, reviewer: Reviewer, c_: ContainerDep
):
    return _review_view(*c_.bank.set_status(reviewer, question_id, body.status))
