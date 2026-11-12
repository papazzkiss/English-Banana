"""Practice endpoints: vocabulary (Phase 2), grammar (3), listening (6), speaking (7),
conversation (8), tutor (9)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Header, Query, UploadFile, status
from fastapi.responses import JSONResponse

from banana_english.api import mappers
from banana_english.api.deps import ERRORS, LLM_ERRORS, ContainerDep, LearnerId
from banana_english.api.schemas import common as c
from banana_english.api.schemas import modules as m
from banana_english.application.use_cases.common import (
    AssessmentFailedError,
    ConflictError,
    NotFoundError,
)
from banana_english.domain.models import Difficulty, Module
from banana_english.domain.services.answer_matching import normalize_answer
from banana_english.infrastructure.observability.metrics import ASSESSMENT_FAILURES, ASSESSMENTS

router = APIRouter(prefix="/api/v1")

# Graded attempts answer synchronously (200) unless the client sends `Prefer: respond-async`
# (RFC 7240). The web app does, because LLM grading can outlast its proxy's request timeout.
PreferHeader = Annotated[
    str | None,
    Header(description="`respond-async`: return 202 with a job; poll GET /jobs/{job_id}"),
]
ASYNC_RESPONSES = {
    202: {
        "model": c.JobResponse,
        "description": "With `Prefer: respond-async`. The job result is the 200 body. Repeating "
        "the same answer while it is still being graded returns the same job.",
    }
}


def _wants_async(prefer: str | None) -> bool:
    return prefer is not None and "respond-async" in prefer.lower()


def _accepted(job) -> JSONResponse:
    return JSONResponse(
        mappers.job(job).model_dump(mode="json"),
        status_code=status.HTTP_202_ACCEPTED,
        headers={"Preference-Applied": "respond-async"},
    )


def _observe(module: Module, fn):
    try:
        outcome = fn()
    except AssessmentFailedError:
        ASSESSMENT_FAILURES.labels(module=module.value).inc()
        raise
    ASSESSMENTS.labels(module=module.value, assessor=outcome.assessment.assessor.value).inc()
    return outcome


# --- vocabulary ------------------------------------------------------------------------


@router.get(
    "/vocabulary/due",
    response_model=m.DueCardsResponse,
    responses=ERRORS,
    tags=["vocabulary"],
    summary="Cards due today, then new cards (daily limit)",
)
def vocabulary_due(
    learner_id: LearnerId, c_: ContainerDep, limit: Annotated[int, Query(ge=1, le=50)] = 20
):
    return m.DueCardsResponse(
        learner_id=learner_id,
        cards=[
            m.DueCardView(
                card_id=d.item.id,
                is_new=d.is_new,
                cefr_level=d.item.cefr_level,
                front=mappers.exercise(d.exercise),
                back=mappers.card_back(d.item),
                state=mappers.card_state(d.card) if d.card else None,
            )
            for d in c_.vocabulary.due(learner_id, limit)
        ],
    )


@router.post(
    "/vocabulary/review",
    response_model=m.ReviewResponse,
    responses=ERRORS,
    tags=["vocabulary"],
    summary="Rate a card (Again/Hard/Good/Easy) -> SM-2 schedule",
)
def vocabulary_review(body: m.ReviewRequest, learner_id: LearnerId, c_: ContainerDep):
    o = _observe(
        Module.VOCABULARY,
        lambda: c_.vocabulary.review(
            learner_id, body.card_id, body.rating, body.answer, body.response_time_ms
        ),
    )
    return m.ReviewResponse(
        attempt_id=o.attempt_id,
        card_id=o.item_id,
        rating_applied=o.extra["rating"],
        assessment=mappers.assessment(o.assessment),
        state=mappers.card_state(o.extra["card"]),
        back=mappers.card_back(o.extra["item"]),
        mastery_changes=[mappers.change(x) for x in o.changes],
        next_recommendation=mappers.recommendation(o.next_recommendation)
        if o.next_recommendation
        else None,
    )


# --- grammar ---------------------------------------------------------------------------


@router.get("/grammar/topics", response_model=list[m.GrammarTopicView], tags=["grammar"])
def grammar_topics(c_: ContainerDep):
    return [
        m.GrammarTopicView(
            skill_id=s.id,
            name=s.name,
            description=s.description,
            exercise_count=len(c_.content.list_exercises(s.id)),
        )
        for s in c_.content.list_skills()
        if s.module is Module.GRAMMAR
    ]


@router.get("/grammar/exercises", response_model=m.GrammarExercisesResponse, tags=["grammar"])
def grammar_exercises(
    c_: ContainerDep, skill_id: str | None = None, difficulty: Difficulty | None = None
):
    items = c_.content.list_all_exercises()
    items = [
        e
        for e in items
        if (not skill_id or e.skill_id == skill_id)
        and (not difficulty or e.difficulty is difficulty)
    ]
    return m.GrammarExercisesResponse(exercises=[mappers.exercise(e) for e in items])


@router.get(
    "/grammar/exercises/{exercise_id}",
    response_model=c.ExerciseView,
    responses=ERRORS,
    tags=["grammar"],
)
def grammar_exercise(exercise_id: str, c_: ContainerDep):
    e = c_.content.get_exercise(exercise_id)
    if e is None or e.module is not Module.GRAMMAR:
        raise NotFoundError(f"exercise {exercise_id}")
    return mappers.exercise(e)


@router.post(
    "/grammar/attempt",
    response_model=c.AttemptResponse,
    responses={**LLM_ERRORS, **ASYNC_RESPONSES},
    tags=["grammar"],
    summary="Submit a grammar answer (rubric-prompted LLM, validated)",
)
def grammar_attempt(
    body: m.GrammarAttemptRequest,
    learner_id: LearnerId,
    c_: ContainerDep,
    prefer: PreferHeader = None,
):
    def grade() -> c.AttemptResponse:
        o = _observe(
            Module.GRAMMAR,
            lambda: c_.grammar.execute(
                learner_id, body.exercise_id, body.answer, body.response_time_ms
            ),
        )
        ex = o.extra["exercise"]
        return mappers.attempt(o, list(ex.accepted_answers), ex.explanation)

    if not _wants_async(prefer):
        return grade()
    c_.grammar.exercise(body.exercise_id)  # 404 now, not inside the job
    return _accepted(
        c_.background.submit(
            learner_id,
            "grammar_assessment",
            f"{body.exercise_id}:{normalize_answer(body.answer)}",
            lambda: grade().model_dump(mode="json"),
        )
    )


# --- listening -------------------------------------------------------------------------


def _lesson_view(lesson) -> m.ListeningLessonView:
    return m.ListeningLessonView(
        id=lesson.id,
        title=lesson.title,
        cefr_level=lesson.cefr_level,
        difficulty=lesson.difficulty,
        duration_seconds=lesson.duration_seconds,
        audio_url=f"/media/listening/{lesson.audio_file}",
        questions=[m.ListeningQuestionView(id=q.id, question=q.question) for q in lesson.questions],
    )


@router.get("/listening/lessons", response_model=m.ListeningLessonsResponse, tags=["listening"])
def listening_lessons(c_: ContainerDep):
    return m.ListeningLessonsResponse(
        lessons=[_lesson_view(x) for x in c_.content.list_listening()]
    )


@router.get(
    "/listening/lessons/{lesson_id}",
    response_model=m.ListeningLessonView,
    responses=ERRORS,
    tags=["listening"],
)
def listening_lesson(lesson_id: str, c_: ContainerDep):
    lesson = c_.content.get_listening(lesson_id)
    if lesson is None:
        raise NotFoundError(f"lesson {lesson_id}")
    return _lesson_view(lesson)


@router.get(
    "/listening/lessons/{lesson_id}/transcript",
    response_model=m.TranscriptResponse,
    responses={**ERRORS, 409: {"model": c.ErrorResponse}},
    tags=["listening"],
    summary="Transcript + answers, available once every question was attempted",
)
def listening_transcript(lesson_id: str, learner_id: LearnerId, c_: ContainerDep):
    lesson = c_.content.get_listening(lesson_id)
    if lesson is None:
        raise NotFoundError(f"lesson {lesson_id}")
    attempted = c_.learner.attempted_item_ids(learner_id)
    if not all(q.id in attempted for q in lesson.questions):
        raise ConflictError("answer every question before viewing the transcript")
    return m.TranscriptResponse(
        lesson_id=lesson.id,
        transcript=lesson.transcript,
        answers={q.id: list(q.accepted_answers) for q in lesson.questions},
    )


@router.post(
    "/listening/attempt",
    response_model=c.AttemptResponse,
    responses={**LLM_ERRORS, **ASYNC_RESPONSES},
    tags=["listening"],
    summary="Answer a comprehension question",
)
def listening_attempt(
    body: m.ListeningAttemptRequest,
    learner_id: LearnerId,
    c_: ContainerDep,
    prefer: PreferHeader = None,
):
    def grade() -> c.AttemptResponse:
        o = _observe(
            Module.LISTENING,
            lambda: c_.listening.execute(
                learner_id, body.question_id, body.answer, body.response_time_ms
            ),
        )
        return mappers.attempt(o, list(o.extra["question"].accepted_answers), None)

    if not _wants_async(prefer):
        return grade()
    c_.listening.question(body.question_id)  # 404 now, not inside the job
    return _accepted(
        c_.background.submit(
            learner_id,
            "listening_assessment",
            f"{body.question_id}:{normalize_answer(body.answer)}",
            lambda: grade().model_dump(mode="json"),
        )
    )


# --- speaking --------------------------------------------------------------------------


@router.get("/speaking/prompts", response_model=m.SpeakingPromptsResponse, tags=["speaking"])
def speaking_prompts(c_: ContainerDep):
    def name_of(skill_id: str | None) -> str | None:
        skill = c_.content.get_skill(skill_id) if skill_id else None
        return skill.name if skill else None

    return m.SpeakingPromptsResponse(
        prompts=[
            m.SpeakingPromptView(
                id=p.id,
                title=p.title,
                cefr_level=p.cefr_level,
                difficulty=p.difficulty,
                instruction=p.instruction,
                target_grammar=p.target_grammar,
                target_grammar_name=name_of(p.target_grammar),
                min_seconds=p.min_seconds,
                max_seconds=p.max_seconds,
            )
            for p in c_.content.list_speaking()
        ]
    )


@router.post(
    "/speaking/attempt",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=c.JobResponse,
    responses=ERRORS,
    tags=["speaking"],
    summary="Upload a spoken answer; poll GET /jobs/{job_id} for transcript + scores",
)
async def speaking_attempt(
    learner_id: LearnerId,
    c_: ContainerDep,
    prompt_id: Annotated[str, Form(pattern=r"^sp\.[a-z]+\.\d{3}$")],
    audio: Annotated[UploadFile, File()],
):
    data = await audio.read(c_.settings.max_upload_mb * 1024 * 1024 + 1)
    job = c_.speaking.submit(learner_id, prompt_id, data, audio.filename or "audio.webm")
    return mappers.job(job)


# --- conversation ----------------------------------------------------------------------


def _conversation(c_, conv) -> m.ConversationView:
    scenario = c_.conversation.scenario_for(conv)
    return m.ConversationView(
        id=conv.id,
        scenario=mappers.scenario(scenario),
        status=conv.status.value,
        turns=[m.TurnView(role=t.role, text=t.text, at=t.at) for t in conv.turns],
        learner_turns_left=max(0, scenario.max_learner_turns - len(conv.learner_turns)),
        summary=conv.summary,
    )


@router.get("/conversation/scenarios", response_model=m.ScenariosResponse, tags=["conversation"])
def scenarios(c_: ContainerDep):
    return m.ScenariosResponse(scenarios=[mappers.scenario(s) for s in c_.content.list_scenarios()])


@router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=m.ConversationView,
    responses=ERRORS,
    tags=["conversation"],
)
def start_conversation(body: m.StartConversationRequest, learner_id: LearnerId, c_: ContainerDep):
    return _conversation(c_, c_.conversation.start(learner_id, body.scenario_id))


@router.get(
    "/conversations/{conversation_id}",
    response_model=m.ConversationView,
    responses=ERRORS,
    tags=["conversation"],
)
def get_conversation(conversation_id: str, learner_id: LearnerId, c_: ContainerDep):
    return _conversation(c_, c_.conversation.get(learner_id, conversation_id))


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=m.ConversationView,
    responses={**LLM_ERRORS, 409: {"model": c.ErrorResponse}},
    tags=["conversation"],
    summary="Send a learner line; the partner replies in character",
)
def send_message(
    conversation_id: str, body: m.MessageRequest, learner_id: LearnerId, c_: ContainerDep
):
    return _conversation(c_, c_.conversation.send(learner_id, conversation_id, body.text))


@router.post(
    "/conversations/{conversation_id}/finish",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=c.JobResponse,
    responses={**ERRORS, 409: {"model": c.ErrorResponse}},
    tags=["conversation"],
    summary="Grade every learner turn (background job)",
)
def finish_conversation(conversation_id: str, learner_id: LearnerId, c_: ContainerDep):
    return mappers.job(c_.conversation.finish(learner_id, conversation_id))


# --- tutor -----------------------------------------------------------------------------


@router.post(
    "/tutor/explain",
    response_model=m.ExplainResponse,
    responses=LLM_ERRORS,
    tags=["tutor"],
    summary="Explain one stored error of an attempt (on demand)",
)
def tutor_explain(body: m.ExplainRequest, learner_id: LearnerId, c_: ContainerDep):
    e = c_.tutor.execute(learner_id, body.attempt_id, body.mistake_index)
    return m.ExplainResponse(
        attempt_id=body.attempt_id,
        error_tag=e.error_tag,
        explanation=e.explanation,
        example=e.example,
        prompt_version=e.prompt_version,
        model=e.model,
    )
