"""LLM test doubles. Neither talks to a network.

* ScriptedLLMProvider  — returns pre-recorded raw outputs in order (tests: malformed JSON,
                         schema violations, provider errors, retries).
* HeuristicMockLLMProvider — dev provider when no model is available. Emits plausible,
                         schema-valid output for every task from the request context. It is NOT
                         a grammar checker; use BANANA_LLM_PROVIDER=ollama for real grading.
"""

from __future__ import annotations

import difflib
import json
from collections import deque
from collections.abc import Iterable

from banana_english.domain.interfaces.llm import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
)
from banana_english.domain.services.answer_matching import normalize_answer

_SKILL_TAG = {
    "grammar.present_simple_continuous": "verb_tense",
    "grammar.past_simple_present_perfect": "verb_tense",
    "grammar.articles": "article",
    "grammar.prepositions_time_place": "preposition",
    "grammar.comparatives_superlatives": "comparative_form",
    "grammar.conditionals": "conditional_structure",
}


class ScriptedLLMProvider(LLMProvider):
    name = "scripted-mock"

    def __init__(self, outputs: Iterable[str | Exception]) -> None:
        self._outputs: deque[str | Exception] = deque(outputs)
        self.requests: list[LLMRequest] = []

    def push(self, *outputs: str | Exception) -> None:
        self._outputs.extend(outputs)

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._outputs:
            raise LLMProviderError("scripted provider has no more outputs")
        output = self._outputs.popleft()
        if isinstance(output, Exception):
            raise output
        return LLMResponse(text=output, model="scripted", input_tokens=10, output_tokens=20)


class HeuristicMockLLMProvider(LLMProvider):
    name = "heuristic-mock"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        handler = {
            "grammar_assessment": self._grammar,
            "listening_assessment": self._listening,
            "conversation_reply": self._reply,
            "tutor_explain": self._tutor,
            "monkey_chat": self._monkey,
        }.get(request.task)
        if handler is None:
            raise LLMProviderError(f"heuristic mock does not support task '{request.task}'")
        return LLMResponse(
            text=handler(request), model="heuristic-mock-v2", input_tokens=0, output_tokens=0
        )

    @staticmethod
    def _similarity(request: LLMRequest) -> tuple[float, str | None]:
        answer = normalize_answer(str(request.context.get("learner_answer", "")))
        refs = [normalize_answer(a) for a in request.context.get("accepted_answers", [])]
        if not refs:
            return 0.0, None
        best = max(refs, key=lambda r: difflib.SequenceMatcher(None, answer, r).ratio())
        return difflib.SequenceMatcher(None, answer, best).ratio(), best

    def _grammar(self, request: LLMRequest) -> str:
        similarity, best = self._similarity(request)
        answer = str(request.context.get("learner_answer", "")).strip()
        if best is None:  # free speech (speaking / conversation): assume acceptable
            return json.dumps(
                {
                    "errors": [],
                    "natural": False,
                    "corrected_answer": None,
                    "feedback": "Mock grading: sounds understandable.",
                }
            )
        tag = _SKILL_TAG.get(str(request.context.get("skill_id")), "other")
        return json.dumps(
            {
                "errors": [
                    {
                        "fragment": answer,
                        "tag": tag,
                        "correction": best,
                        "explanation": "Mock grading: compare with the model answer.",
                    }
                ],
                "natural": False,
                "corrected_answer": best,
                "feedback": "Not quite. Compare your answer with the model answer.",
            }
        )

    def _listening(self, request: LLMRequest) -> str:
        similarity, _ = self._similarity(request)
        understood = "fully" if similarity >= 0.8 else ("partly" if similarity >= 0.5 else "not")
        return json.dumps(
            {
                "understood": understood,
                "feedback": "Mock grading: "
                + ("close enough." if understood == "fully" else "listen again for the detail."),
            }
        )

    @staticmethod
    def _reply(request: LLMRequest) -> str:
        turn = int(request.context.get("turn", 0))
        lines = [
            "Sure! Anything else?",
            "Great choice. What else would you like?",
            "No problem at all.",
            "Of course. Is there anything else I can help with?",
            "Perfect. Have a lovely day!",
        ]
        return lines[(turn // 2) % len(lines)]

    @staticmethod
    def _monkey(request: LLMRequest) -> str:
        lines = [
            "Hi! I'm AI Monkey. What would you like to talk about today?",
            "That sounds fun! Can you tell me more about it?",
            "Oh, interesting! How did that make you feel?",
            "I love that! Bananas make everything better. What else do you enjoy?",
        ]
        return lines[int(request.context.get("turn", 0)) // 2 % len(lines)]

    @staticmethod
    def _tutor(request: LLMRequest) -> str:
        tag = str(request.context.get("error_tag", "grammar")).replace("_", " ")
        correct = request.context.get("correct_form") or "the corrected sentence"
        return json.dumps(
            {
                "explanation": f'This is a {tag} error. The correct form is "{correct}" because '
                "English uses this pattern here. (Mock tutor: enable a real LLM for "
                "a full explanation.)",
                "example": "She has lived in Hanoi since 2019.",
            }
        )
