"""Production LLM wiring: configuration, the Ollama provider, fallback, retries and call logs."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from pydantic import BaseModel

from banana_english.application.services.conversation import ConversationPartner
from banana_english.application.services.monkey import MonkeyChat, MonkeyTurn
from banana_english.application.services.structured_llm import StructuredLLM
from banana_english.config.settings import Settings
from banana_english.domain.interfaces.assessment import AssessmentUnavailableError
from banana_english.domain.interfaces.llm import (
    LLMMessage,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)
from banana_english.infrastructure.ai.factory import build_llm_provider
from banana_english.infrastructure.ai.fallback import FallbackLLMProvider
from banana_english.infrastructure.ai.instrumented import InstrumentedLLMProvider
from banana_english.infrastructure.ai.mock_llm import ScriptedLLMProvider
from banana_english.infrastructure.ai.ollama_provider import OllamaProvider, chat_body
from banana_english.infrastructure.cache.caches import MemoryCache

MODEL = "qwen3:30b-a3b-q4_K_M"
REQUEST = LLMRequest(
    task="monkey_chat",
    messages=(LLMMessage("system", "Be kind."), LLMMessage("user", "Hi!")),
    prompt_version="v1",
    temperature=0.8,
    max_output_tokens=200,
)
OLLAMA_REPLY = {
    "model": MODEL,
    "message": {"role": "assistant", "content": "Hello!"},
    "prompt_eval_count": 42,
    "eval_count": 16,
    "eval_duration": 2_000_000_000,
    "prompt_eval_duration": 1_500_000_000,
    "load_duration": 3_000_000,
    "total_duration": 3_600_000_000,
}


def ollama(handler, **kwargs) -> OllamaProvider:
    kwargs.setdefault("num_ctx", 8192)
    return OllamaProvider(
        "http://ollama:11434", MODEL, transport=httpx.MockTransport(handler), **kwargs
    )


def reply_with(body: dict, sent: list[dict] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if sent is not None:
            sent.append({"path": request.url.path, **json.loads(request.content)})
        return httpx.Response(200, json=body)

    return handler


# --- configuration ---------------------------------------------------------------------------


def test_settings_defaults_and_compose_empty_values(monkeypatch):
    for name, value in {
        "BANANA_OLLAMA_MODEL": MODEL,
        "BANANA_LLM_TEMPERATURE": "",  # ${LLM_TEMPERATURE:-} in docker-compose.yml
        "BANANA_LLM_MAX_OUTPUT_TOKENS": "",
        "BANANA_LLM_FALLBACK_MODEL": " ",
    }.items():
        monkeypatch.setenv(name, value)
    s = Settings()
    assert s.ollama_model == MODEL
    assert s.llm_temperature is None and s.llm_max_output_tokens is None
    assert s.llm_fallback_model is None
    assert (s.llm_context_length, s.llm_timeout_seconds, s.llm_keep_alive) == (8192, 180.0, "30m")


def test_settings_read_overrides_from_env(monkeypatch):
    monkeypatch.setenv("BANANA_LLM_TEMPERATURE", "0.3")
    monkeypatch.setenv("BANANA_LLM_MAX_OUTPUT_TOKENS", "256")
    monkeypatch.setenv("BANANA_LLM_CONTEXT_LENGTH", "4096")
    monkeypatch.setenv("BANANA_LLM_TIMEOUT_SECONDS", "90")
    s = Settings()
    assert (s.llm_temperature, s.llm_max_output_tokens) == (0.3, 256)
    assert (s.llm_context_length, s.llm_timeout_seconds) == (4096, 90.0)


def test_python_code_has_no_default_model():
    assert Settings.model_fields["ollama_model"].default is None
    with pytest.raises(ValueError, match="BANANA_OLLAMA_MODEL"):
        build_llm_provider(Settings(llm_provider="ollama"))


def test_factory_builds_the_configured_model():
    llm = build_llm_provider(
        Settings(
            llm_provider="ollama",
            ollama_url="http://ollama:11434/",
            ollama_model=MODEL,
            llm_context_length=4096,
            llm_timeout_seconds=90,
            llm_keep_alive="1h",
        )
    )
    assert isinstance(llm, OllamaProvider)
    assert (llm.name, llm.model, llm.base_url) == (f"ollama:{MODEL}", MODEL, "http://ollama:11434")
    assert (llm.num_ctx, llm.timeout_seconds, llm.keep_alive) == (4096, 90, "1h")


def test_factory_adds_a_fallback_only_when_configured():
    base = {"llm_provider": "ollama", "ollama_model": MODEL}
    assert isinstance(build_llm_provider(Settings(**base)), OllamaProvider)
    same = Settings(**base, llm_fallback_model=MODEL)
    assert isinstance(build_llm_provider(same), OllamaProvider)
    llm = build_llm_provider(Settings(**base, llm_fallback_model="qwen3:4b-instruct"))
    assert isinstance(llm, FallbackLLMProvider)
    assert llm.name == f"ollama:{MODEL}"  # cache keys and metrics stay on the production model
    assert llm.fallback.name == "ollama:qwen3:4b-instruct"
    assert llm.fallback.keep_alive == "5m"


# --- Ollama provider ---------------------------------------------------------------------------


def test_request_body_keeps_task_settings_and_adds_context_length():
    sent: list[dict] = []
    response = ollama(reply_with(OLLAMA_REPLY, sent)).complete(REQUEST)
    body = sent[0]
    assert body["path"] == "/api/chat"
    assert (body["model"], body["think"], body["stream"], body["keep_alive"]) == (
        MODEL,
        False,
        False,
        "30m",
    )
    assert body["options"] == {
        "temperature": 0.8,
        "top_p": 0.8,  # Qwen3 non-thinking sampling
        "top_k": 20,
        "min_p": 0.0,
        "num_predict": 200,
        "num_ctx": 8192,
    }
    assert response.text == "Hello!" and response.model == MODEL
    assert (response.input_tokens, response.output_tokens) == (42, 16)
    assert response.tokens_per_second == 8.0
    assert response.stats == {
        "load_ms": 3.0,
        "prompt_eval_ms": 1500.0,
        "eval_ms": 2000.0,
        "total_ms": 3600.0,
        "think": 0.0,
        "thinking_chars": 0.0,
    }
    assert response.fallback is False


THINK_REQUEST = LLMRequest(
    task="tutor_explain",
    messages=REQUEST.messages,
    prompt_version="v1",
    temperature=0.0,
    max_output_tokens=300,
    think=True,
)


def test_thinking_requests_reason_first_and_return_only_the_answer():
    sent: list[dict] = []
    reply = {**OLLAMA_REPLY, "message": {"content": "Use 'went'.", "thinking": "step 1 ..."}}
    response = ollama(reply_with(reply, sent), think_budget=1024).complete(THINK_REQUEST)
    body = sent[0]
    assert body["think"] is True
    # the answer keeps its budget, the reasoning gets its own; never greedy while thinking
    assert body["options"]["num_predict"] == 300 + 1024
    assert body["options"]["temperature"] == 0.6 and body["options"]["top_p"] == 0.95
    assert response.text == "Use 'went'." and "step 1" not in response.text
    assert response.stats["think"] == 1.0 and response.stats["thinking_chars"] == 10.0


def test_thinking_can_be_switched_off():
    sent: list[dict] = []
    ollama(reply_with(OLLAMA_REPLY, sent), thinking=False).complete(THINK_REQUEST)
    assert sent[0]["think"] is False and sent[0]["options"]["num_predict"] == 300


def test_reasoning_that_uses_the_whole_budget_is_answered_without_thinking(caplog):
    sent: list[dict] = []
    replies = iter(
        [
            {**OLLAMA_REPLY, "message": {"content": "", "thinking": "long " * 500}},
            {**OLLAMA_REPLY, "message": {"content": "Use 'went'."}},
        ]
    )

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=next(replies))

    with caplog.at_level(logging.WARNING, "banana_english.llm"):
        response = ollama(handler).complete(THINK_REQUEST)
    assert [b["think"] for b in sent] == [True, False]
    assert response.text == "Use 'went'." and response.stats["think"] == 0.0
    assert "llm_think_exhausted" in caplog.text


def test_configured_overrides_replace_temperature_and_cap_tokens():
    sent: list[dict] = []
    llm = ollama(reply_with(OLLAMA_REPLY, sent), temperature=0.1, max_output_tokens=150)
    llm.complete(REQUEST)
    llm.complete(LLMRequest("t", REQUEST.messages, "v1", max_output_tokens=60))
    assert sent[0]["options"]["temperature"] == 0.1
    assert sent[0]["options"]["num_predict"] == 150  # capped
    assert sent[1]["options"]["num_predict"] == 60  # already below the cap


def test_benchmark_body_is_unchanged_without_provider_options():
    body = chat_body(MODEL, REQUEST, "30m")
    assert body["think"] is False
    assert body["options"] == {
        "temperature": 0.8,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
        "num_predict": 200,
    }


def test_missing_model_error_says_how_to_build_it():
    def handler(_):
        return httpx.Response(404, json={"error": f"model '{MODEL}' not found"})

    with pytest.raises(LLMProviderError, match="not found.*setup_ollama_model") as exc:
        ollama(handler).complete(REQUEST)
    assert not isinstance(exc.value, LLMTimeoutError)


def test_timeout_is_a_distinct_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMTimeoutError, match="did not answer within 180s"):
        ollama(handler, timeout_seconds=180).complete(REQUEST)


def test_warm_up_loads_the_model_with_the_request_context_size(caplog):
    sent: list[dict] = []
    with caplog.at_level(logging.INFO, "banana_english.llm"):
        ollama(reply_with({"done": True}, sent)).warm_up()
    assert sent == [
        {"path": "/api/generate", "model": MODEL, "keep_alive": "30m", "options": {"num_ctx": 8192}}
    ]
    assert f"llm_ready model={MODEL} num_ctx=8192" in caplog.text


def test_warm_up_never_raises_and_logs_why(caplog):
    def missing(_):
        return httpx.Response(404, json={"error": "model not found"})

    def down(request):
        raise httpx.ConnectError("refused", request=request)

    with caplog.at_level(logging.INFO, "banana_english.llm"):
        ollama(missing).warm_up()
        ollama(down).warm_up()
    assert caplog.text.count("llm_unavailable") == 2
    assert "setup_ollama_model" in caplog.text and "not reachable" in caplog.text


# --- fallback --------------------------------------------------------------------------------


def named(outputs, name):
    llm = ScriptedLLMProvider(outputs)
    llm.name = name
    return llm


def test_fallback_answers_when_the_primary_is_unavailable(caplog):
    primary = named([LLMProviderError("ollama 404: model not found")], "ollama:primary")
    fallback = named(["hi"], "ollama:small")
    with caplog.at_level(logging.WARNING, "banana_english.llm"):
        response = FallbackLLMProvider(primary, fallback).complete(REQUEST)
    assert response.fallback is True and response.text == "hi"
    assert "llm_fallback task=monkey_chat primary=ollama:primary fallback=ollama:small" in (
        caplog.text
    )


def test_no_fallback_on_timeout():
    fallback = named(["hi"], "ollama:small")
    llm = FallbackLLMProvider(named([LLMTimeoutError("slow")], "ollama:primary"), fallback)
    with pytest.raises(LLMTimeoutError):
        llm.complete(REQUEST)
    assert fallback.requests == []


def test_both_models_failing_reports_both():
    llm = FallbackLLMProvider(
        named([LLMProviderError("primary down")], "p"),
        named([LLMProviderError("fallback down")], "f"),
    )
    with pytest.raises(LLMProviderError, match="primary down.*fallback down"):
        llm.complete(REQUEST)


# --- retries -----------------------------------------------------------------------------------


class Verdict(BaseModel):
    ok: bool


def test_structured_output_is_not_retried_after_a_timeout():
    llm = ScriptedLLMProvider([LLMTimeoutError("slow"), '{"ok": true}'])
    with pytest.raises(AssessmentUnavailableError) as exc:
        StructuredLLM(llm, max_retries=1).run(REQUEST, Verdict)
    assert len(llm.requests) == 1 and exc.value.attempts == 1


def test_structured_output_retries_other_errors_and_logs_it(caplog):
    llm = ScriptedLLMProvider([LLMProviderError("500"), '{"ok": true}'])
    with caplog.at_level(logging.WARNING, "banana_english.llm"):
        verdict, _ = StructuredLLM(llm, max_retries=1).run(REQUEST, Verdict)
    assert verdict.ok and len(llm.requests) == 2
    assert "llm_retry task=monkey_chat attempt=2/2 after: provider error: 500" in caplog.text


def test_fallback_verdict_is_used_but_never_cached():
    class Fallback(ScriptedLLMProvider):
        def complete(self, request):
            response = super().complete(request)
            return LLMResponse(response.text, "small", fallback=True)

    cache = MemoryCache()
    verdict, model = StructuredLLM(Fallback(['{"ok": true}']), cache).run(REQUEST, Verdict, "k")
    assert verdict.ok and model == "small"
    assert cache.get("k") is None


def test_chat_replies_are_not_retried_after_a_timeout(content):
    scenario = content.list_scenarios()[0]
    partner_llm = ScriptedLLMProvider([LLMTimeoutError("slow"), "Hi"])
    with pytest.raises(LLMProviderError, match="slow"):
        ConversationPartner(partner_llm, max_retries=1).reply(scenario, [])
    assert len(partner_llm.requests) == 1

    monkey_llm = ScriptedLLMProvider([LLMTimeoutError("slow"), "Hi"])
    with pytest.raises(LLMProviderError, match="slow"):
        MonkeyChat(monkey_llm, max_retries=1).reply("B1", [MonkeyTurn("learner", "Hello")])
    assert len(monkey_llm.requests) == 1


def test_only_the_reasoning_tasks_think(content):
    """Qwen3 thinking where it helps (error analysis, explanations); instant replies elsewhere."""
    from banana_english.application.services.grammar_assessment import (
        LLMGrammarAssessmentEngine,
    )

    exercise = content.get_exercise("gr.past.004")
    grammar = LLMGrammarAssessmentEngine(StructuredLLM(ScriptedLLMProvider([])))
    assert grammar.build_request(exercise, "I have saw it").think is True

    monkey_llm = ScriptedLLMProvider(["Hi there!", "Present perfect: have + past participle."])
    monkey = MonkeyChat(monkey_llm, max_retries=0)
    monkey.reply("B1", [MonkeyTurn("learner", "Hello, how are you?")])
    monkey.reply("B1", [MonkeyTurn("learner", "Explain the present perfect in detail, please.")])
    small_talk, explanation = monkey_llm.requests
    assert small_talk.think is False and explanation.think is True

    scenario = content.list_scenarios()[0]
    partner_llm = ScriptedLLMProvider(["Welcome!"])
    ConversationPartner(partner_llm, max_retries=0).reply(scenario, [])
    assert partner_llm.requests[0].think is False


# --- observability -----------------------------------------------------------------------------


def test_every_call_logs_model_latency_tokens_and_speed(caplog):
    llm = InstrumentedLLMProvider(ollama(reply_with(OLLAMA_REPLY)))
    with caplog.at_level(logging.INFO, "banana_english.llm"):
        llm.complete(REQUEST)
    line = next(r.getMessage() for r in caplog.records if "llm_call" in r.getMessage())
    for part in (
        f"model={MODEL}",
        "input_tokens=42",
        "output_tokens=16",
        "tok_s=8.0",
        "prompt_eval_ms=1500.0",
        "fallback=False",
        "ok=True",
    ):
        assert part in line
    assert "latency_ms=" in line


def test_failed_calls_log_the_error(caplog):
    llm = InstrumentedLLMProvider(named([LLMTimeoutError("did not answer within 180s")], "p"))
    with caplog.at_level(logging.INFO, "banana_english.llm"), pytest.raises(LLMTimeoutError):
        llm.complete(REQUEST)
    record = next(r for r in caplog.records if "llm_call" in r.getMessage())
    assert record.levelno == logging.WARNING
    assert "ok=False error=did not answer within 180s" in record.getMessage()


def test_the_log_counts_llm_calls_per_request(caplog):
    from banana_english.infrastructure.observability.context import reset_request_id, set_request_id

    llm = InstrumentedLLMProvider(named(["a", "b", "c"], "p"))
    with caplog.at_level(logging.INFO, "banana_english.llm"):
        token = set_request_id("req-1")
        llm.complete(REQUEST)
        llm.complete(REQUEST)  # a second inference in the same request
        reset_request_id(token)
        token = set_request_id("req-2")
        llm.complete(REQUEST)
        reset_request_id(token)
    counts = [
        r.getMessage().split("call_n=")[1].split()[0]
        for r in caplog.records
        if "llm_call" in r.getMessage()
    ]
    assert counts == ["1", "2", "1"]
