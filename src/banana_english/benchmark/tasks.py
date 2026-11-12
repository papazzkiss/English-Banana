"""Turn a benchmark test into the exact LLMRequest production would send, and parse the
model's reply the way production does.

Production prompts are not copied: the request is captured from the real services
(LLMGrammarAssessmentEngine, Tutor, ConversationPartner, MonkeyChat) through a recording
provider, so a prompt change in the app is automatically benchmarked. Only two categories have
no production prompt (vocabulary, complex questions); their prompts are versioned below.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from banana_english.application.services.conversation import ConversationPartner, sanitize_reply
from banana_english.application.services.grammar_assessment import LLMGrammarAssessmentEngine
from banana_english.application.services.llm_contracts import (
    GrammarVerdict,
    InvalidLLMOutputError,
    TutorExplanation,
    parse_llm_json,
    strip_reasoning,
)
from banana_english.application.services.monkey import (
    CHAT_CHARS,
    DETAILED_CHARS,
    DETAILED_TOKENS,
    MonkeyChat,
    MonkeyTurn,
    clean_reply,
)
from banana_english.application.services.structured_llm import StructuredLLM
from banana_english.application.services.tutor import Tutor
from banana_english.domain.interfaces.llm import (
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)
from banana_english.domain.interfaces.repositories import ContentRepository
from banana_english.domain.models import ConversationTurn, Mistake, MistakeCategory

BENCH_VOCAB_VERSION = "bench_vocabulary_v1"
BENCH_COMPLEX_VERSION = "bench_complex_question_v1"

VOCAB_SYSTEM = """\
You are an English teacher writing a vocabulary card for a CEFR {level} learner.
Explain the word in simple English.
Respond with ONLY this JSON, no other text:
{{"definition": <one short sentence, do not use the word itself>,
"example": <one natural example sentence that uses the word>,
"synonym": <one common synonym>}}
"""

VOCAB_SCHEMA = {
    "type": "object",
    "properties": {
        "definition": {"type": "string"},
        "example": {"type": "string"},
        "synonym": {"type": "string"},
    },
    "required": ["definition", "example", "synonym"],
    "additionalProperties": False,
}

COMPLEX_SYSTEM = """\
You are an expert English teacher answering a learner's question about English.
- Start with a one-sentence direct answer.
- Then explain the rule clearly with one or two short examples.
- Use at most 120 words, plain text, no headings and no markdown.
"""


@dataclass
class Parsed:
    """What the checks look at: the raw reply, the cleaned text and named fields."""

    raw: str
    text: str
    contract_ok: bool = True
    contract_error: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)


class _Recorder(LLMProvider):
    """Captures the request a production service builds; answers with a canned reply."""

    name = "benchmark-recorder"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(self.reply, model=self.name)


_CANNED_TUTOR = json.dumps({"explanation": "x" * 30, "example": "A new example sentence."})


def build_request(test: dict, content: ContentRepository) -> LLMRequest:
    src = test["source"]
    kind = src["kind"]
    if kind == "grammar_assessment":
        exercise = _exercise(content, src["exercise_id"])
        return LLMGrammarAssessmentEngine(StructuredLLM(_Recorder("{}"))).build_request(
            exercise, src["answer"]
        )
    if kind == "tutor":
        exercise = _exercise(content, src["exercise_id"])
        rec = _Recorder(_CANNED_TUTOR)
        Tutor(StructuredLLM(rec, cache=None, max_retries=0)).explain(
            Mistake(
                MistakeCategory(src["error_tag"]), src["assessor_note"], None, src["correct_form"]
            ),
            src["answer"],
            src["correct_form"],
            exercise.cefr_level.value,
            teacher_rule=exercise.explanation,
            task=f"{exercise.instruction} {exercise.prompt}",
        )
        return rec.requests[0]
    if kind == "conversation":
        scenario = next(s for s in content.list_scenarios() if s.id == src["scenario_id"])
        turns = [ConversationTurn("assistant", scenario.opening_line, datetime.now(UTC))]
        turns += [ConversationTurn(t["role"], t["text"], datetime.now(UTC)) for t in src["turns"]]
        rec = _Recorder("ok")
        ConversationPartner(rec, max_retries=0).reply(scenario, turns)
        return rec.requests[0]
    if kind == "monkey":
        rec = _Recorder("ok")
        MonkeyChat(rec, max_retries=0).reply(
            src["level"], [MonkeyTurn(t["role"], t["text"]) for t in src["turns"]]
        )
        return rec.requests[0]
    if kind == "vocabulary":
        return LLMRequest(
            task="bench_vocabulary",
            prompt_version=BENCH_VOCAB_VERSION,
            messages=(
                LLMMessage("system", VOCAB_SYSTEM.format(level=src["level"])),
                LLMMessage("user", f"Word: {src['word']}"),
            ),
            response_schema=VOCAB_SCHEMA,
            temperature=0.2,
            max_output_tokens=200,
        )
    if kind == "complex":
        return LLMRequest(
            task="bench_complex_question",
            prompt_version=BENCH_COMPLEX_VERSION,
            messages=(LLMMessage("system", COMPLEX_SYSTEM), LLMMessage("user", src["question"])),
            temperature=0.2,
            max_output_tokens=300,
        )
    raise ValueError(f"unknown test kind: {kind}")


def parse_output(test: dict, raw: str, content: ContentRepository) -> Parsed:
    src = test["source"]
    kind = src["kind"]
    visible = strip_reasoning(raw)
    if kind == "grammar_assessment":
        exercise = _exercise(content, src["exercise_id"])
        try:
            verdict = parse_llm_json(raw, GrammarVerdict, context={"answer": src["answer"]})
        except InvalidLLMOutputError as exc:
            return Parsed(raw, visible, False, str(exc)[:200])
        assessment = verdict.to_assessment("bench", "bench")
        # where the model says the mistake is (fragment) + why (explanation) + feedback
        notes = " ".join(
            [verdict.feedback] + [f"{e.fragment} {e.explanation}" for e in verdict.errors]
        )
        return Parsed(
            raw,
            verdict.feedback,
            fields={
                "is_correct": assessment.is_correct,
                "corrected_answer": verdict.corrected_answer or "",
                "references": list(exercise.accepted_answers),
                "feedback": verdict.feedback,
                "notes": notes,
            },
        )
    if kind == "tutor":
        try:
            out = parse_llm_json(raw, TutorExplanation, context={"answer": src["answer"]})
        except InvalidLLMOutputError as exc:
            return Parsed(raw, visible, False, str(exc)[:200])
        return Parsed(
            raw,
            out.explanation,
            fields={
                "explanation": out.explanation,
                "example": out.example,
            },
        )
    if kind == "conversation":
        return Parsed(raw, sanitize_reply(raw))
    if kind == "monkey":
        # the same cleaning and length limit production applies to this request
        detailed = build_request(test, content).max_output_tokens == DETAILED_TOKENS
        return Parsed(raw, clean_reply(raw, DETAILED_CHARS if detailed else CHAT_CHARS))
    if kind == "vocabulary":
        try:
            data = _loose_json(visible)
            if not all(
                isinstance(data.get(k), str) and data[k].strip()
                for k in ("definition", "example", "synonym")
            ):
                raise ValueError("missing keys")
        except ValueError as exc:
            return Parsed(raw, visible, False, str(exc)[:200])
        return Parsed(raw, data["definition"], fields=dict(data))
    if kind == "complex":
        return Parsed(raw, visible)
    raise ValueError(f"unknown test kind: {kind}")


def _exercise(content: ContentRepository, exercise_id: str):
    exercise = content.get_exercise(exercise_id)
    if exercise is None:
        raise ValueError(f"unknown exercise {exercise_id}")
    return exercise


def _loose_json(text: str) -> dict:
    fenced = re.match(r"^```(?:json)?\s*\n(.*)\n```$", text.strip(), re.DOTALL)
    data = json.loads(fenced.group(1) if fenced else text)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data
