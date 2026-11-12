from __future__ import annotations

from banana_english.config.settings import Settings
from banana_english.domain.interfaces.llm import LLMProvider
from banana_english.domain.interfaces.stt import STTProvider
from banana_english.domain.interfaces.tts import TTSProvider
from banana_english.infrastructure.ai.mock_llm import HeuristicMockLLMProvider
from banana_english.infrastructure.stt.mock_stt import MockSTTProvider
from banana_english.infrastructure.tts.mock_tts import MockTTSProvider


def build_llm_provider(settings: Settings) -> LLMProvider:
    """The only place that knows concrete LLM provider classes."""
    if settings.llm_provider == "mock":
        return HeuristicMockLLMProvider()
    if settings.llm_provider == "ollama":
        from banana_english.infrastructure.ai.fallback import FallbackLLMProvider
        from banana_english.infrastructure.ai.ollama_provider import OllamaProvider

        if not settings.ollama_model:
            raise ValueError(
                "BANANA_OLLAMA_MODEL is not set "
                "(production: Qwen3-30B-A3B, see .env.example and docs/QWEN3_30B.md)"
            )

        def ollama(model: str, keep_alive: str) -> OllamaProvider:
            return OllamaProvider(
                settings.ollama_url,
                model,
                timeout_seconds=settings.llm_timeout_seconds,
                keep_alive=keep_alive,
                num_ctx=settings.llm_context_length,
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_output_tokens,
                thinking=settings.llm_thinking,
                think_budget=settings.llm_think_budget,
            )

        primary = ollama(settings.ollama_model, settings.llm_keep_alive)
        fallback = settings.llm_fallback_model
        if not fallback or fallback == settings.ollama_model:
            return primary
        return FallbackLLMProvider(primary, ollama(fallback, settings.llm_fallback_keep_alive))
    raise ValueError(f"unknown LLM provider: {settings.llm_provider}")


def build_stt_provider(settings: Settings) -> STTProvider:
    if settings.stt_provider == "mock":
        return MockSTTProvider()
    if settings.stt_provider == "whisper":
        from banana_english.infrastructure.stt.faster_whisper_provider import (
            FasterWhisperProvider,
        )

        return FasterWhisperProvider(settings.whisper_model)
    raise ValueError(f"unknown STT provider: {settings.stt_provider}")


def build_tts_provider(settings: Settings) -> TTSProvider:
    if settings.tts_provider == "mock":
        return MockTTSProvider()
    if settings.tts_provider == "piper":
        from banana_english.infrastructure.tts.piper_provider import PiperTTSProvider

        return PiperTTSProvider(settings.tts_voice, settings.tts_model_dir)
    raise ValueError(f"unknown TTS provider: {settings.tts_provider}")
