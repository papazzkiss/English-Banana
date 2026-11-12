"""AI Monkey: free chat with a friendly monkey, typed or spoken. Independent of the scripted
conversation (Phase 8) and of mastery; hidden behind BANANA_FEATURE_AI_MONKEY."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from banana_english.api.deps import ERRORS, ContainerDep, LearnerId
from banana_english.api.schemas import common as c
from banana_english.api.schemas import modules as m
from banana_english.application.services.language_policy import LanguagePreferences, TurnPolicy
from banana_english.application.services.monkey import MonkeyTurn
from banana_english.application.use_cases.common import NotFoundError


def _enabled(c_: ContainerDep) -> None:
    if not c_.settings.feature_ai_monkey:
        raise NotFoundError("AI Monkey is not enabled")


def _policy_view(policy: TurnPolicy | None) -> m.MonkeyPolicyView | None:
    if policy is None:
        return None
    return m.MonkeyPolicyView(
        **{k: v for k, v in asdict(policy).items() if k in m.MonkeyPolicyView.model_fields}
    )


router = APIRouter(prefix="/api/v1/monkey", tags=["ai-monkey"], dependencies=[Depends(_enabled)])


@router.post(
    "/chat",
    response_model=m.MonkeyChatResponse,
    responses={
        **ERRORS,
        503: {"model": c.ErrorResponse, "description": "The model is unavailable"},
    },
    summary="Send the conversation so far and get AI Monkey's reply",
)
def chat(body: m.MonkeyChatRequest, learner_id: LearnerId, c_: ContainerDep):
    turns = [MonkeyTurn(x.role, x.text.strip()) for x in body.messages]
    prefs = LanguagePreferences(**body.preferences.model_dump()) if body.preferences else None
    r = c_.monkey.reply(learner_id, turns, prefs)
    return m.MonkeyChatResponse(
        reply=r.text,
        prompt_version=r.prompt_version,
        model=r.model,
        preferences=m.MonkeyPreferencesView(**asdict(r.preferences)),
        policy=_policy_view(r.policy),
        changes=list(r.policy.changes) if r.policy else [],
    )


@router.post(
    "/transcribe",
    response_model=m.MonkeyTranscriptResponse,
    responses=ERRORS,
    summary="Transcribe a short voice message (the audio is not kept)",
)
async def transcribe(learner_id: LearnerId, c_: ContainerDep, audio: Annotated[UploadFile, File()]):
    data = await audio.read(c_.settings.max_upload_mb * 1024 * 1024 + 1)
    # Whisper takes about a second per message: keep it off the event loop.
    t = await run_in_threadpool(c_.monkey_ears.transcribe, data, audio.filename or "audio.webm")
    return m.MonkeyTranscriptResponse(text=t.text.strip(), duration_seconds=t.duration_seconds)


@router.post(
    "/speech",
    response_class=Response,
    responses={
        200: {"content": {"audio/wav": {}}, "description": "WAV (16-bit PCM) of the text"},
        **ERRORS,
        503: {"model": c.ErrorResponse, "description": "The voice is unavailable"},
    },
    summary="AI Monkey's voice: synthesise a reply on the server (Piper)",
)
def speech(body: m.MonkeySpeechRequest, learner_id: LearnerId, c_: ContainerDep):
    audio = c_.monkey_voice.speak(body.text)
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
