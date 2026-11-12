"""Prometheus metrics exposed at /metrics. LLM/STT latency and cost grow with usage and are
the two costs most likely to leak, so they are measured per provider and task."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

_LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120, 180, 300)

LLM_LATENCY = Histogram(
    "banana_llm_call_seconds", "LLM call latency", ["provider", "task"], buckets=_LATENCY_BUCKETS
)
LLM_CALLS = Counter("banana_llm_calls_total", "LLM calls", ["provider", "task", "outcome"])
LLM_TOKENS = Counter("banana_llm_tokens_total", "LLM tokens", ["provider", "task", "kind"])
LLM_TOKENS_PER_SECOND = Histogram(
    "banana_llm_output_tokens_per_second",
    "LLM generation speed, as reported by the runtime",
    ["provider", "task"],
    buckets=(1, 2, 4, 6, 8, 10, 15, 20, 30, 50, 100),
)
LLM_FALLBACKS = Counter(
    "banana_llm_fallbacks_total",
    "Requests answered by the configured fallback model",
    ["primary", "fallback", "task"],
)
LLM_COST = Counter(
    "banana_llm_cost_usd_total",
    "Estimated LLM cost (configurable per 1k tokens; 0 for local)",
    ["provider", "task"],
)
STT_LATENCY = Histogram(
    "banana_stt_seconds", "STT transcription latency", ["provider"], buckets=_LATENCY_BUCKETS
)
STT_AUDIO_SECONDS = Counter(
    "banana_stt_audio_seconds_total", "Audio seconds transcribed", ["provider"]
)
STT_CALLS = Counter("banana_stt_calls_total", "STT calls", ["provider", "outcome"])
TTS_LATENCY = Histogram(
    "banana_tts_seconds", "TTS synthesis latency", ["provider"], buckets=_LATENCY_BUCKETS
)
TTS_CALLS = Counter("banana_tts_calls_total", "TTS calls", ["provider", "outcome"])
HTTP_LATENCY = Histogram(
    "banana_http_request_seconds",
    "HTTP request latency",
    ["method", "route", "status"],
    buckets=_LATENCY_BUCKETS,
)
ASSESSMENTS = Counter(
    "banana_assessments_total", "Assessments by module and assessor", ["module", "assessor"]
)
ASSESSMENT_FAILURES = Counter(
    "banana_assessment_failures_total", "Assessments that could not be produced", ["module"]
)
