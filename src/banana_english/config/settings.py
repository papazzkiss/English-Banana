from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration. Every field can be set via BANANA_<FIELD> env vars."""

    model_config = SettingsConfigDict(env_prefix="BANANA_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'banana_english.db'}"
    content_dir: Path = PROJECT_ROOT / "content"
    upload_dir: Path = PROJECT_ROOT / "var/uploads"
    redis_url: str | None = None  # None -> in-process cache

    # Serve AI-generated content only after human approval.
    require_reviewed_content: bool = False

    llm_provider: Literal["mock", "ollama"] = "mock"
    ollama_url: str = "http://127.0.0.1:11434"
    # The Ollama model (BANANA_OLLAMA_MODEL); required with llm_provider=ollama. Production
    # (docker-compose.yml, .env.example) uses Qwen3-30B-A3B, set up by
    # scripts/setup_ollama_model.sh (docs/QWEN3_30B.md). Deliberately no default here: the
    # model is configuration.
    ollama_model: str | None = None
    # Local CPU/GPU inference: a long chat prompt with nothing cached, plus reasoning for the
    # tasks that think, takes minutes in the worst case. The web proxy timeout derives from it.
    llm_timeout_seconds: float = 180.0
    llm_max_retries: int = 1  # retries after an error or invalid output; never after a timeout
    # Context window (num_ctx) sent with every request. 8192 holds AI Monkey's longest history
    # (12 turns x 1000 chars, more tokens when learners type Vietnamese) without truncation.
    llm_context_length: int = 8192
    llm_temperature: float | None = None  # None: each task keeps its tuned temperature
    llm_max_output_tokens: int | None = None  # None: each task's own limit; else an upper bound
    llm_keep_alive: str = "30m"  # how long Ollama keeps the model in RAM after the last request
    llm_warm_up: bool = True  # load the model when the API starts, not on the first request
    # Qwen3 thinking: tasks that ask for it (explanations, judging an answer) reason before
    # answering; the reasoning is dropped, only the answer is used. false = never think.
    llm_thinking: bool = True
    llm_think_budget: int = 1024  # reasoning tokens allowed on top of the answer's own budget
    # Optional second model, used only when the primary is unavailable (never on a timeout).
    # Unset -> no fallback: the production model never changes silently.
    llm_fallback_model: str | None = None
    llm_fallback_keep_alive: str = "5m"  # free the fallback's RAM soon after it is used
    llm_cost_per_1k_tokens: float = 0.0  # 0 for a local model; set for hosted APIs

    stt_provider: Literal["mock", "whisper"] = "mock"
    whisper_model: str = "base.en"
    # AI Monkey's voice. Browsers cannot be relied on to speak (Brave on Linux has no voices).
    tts_provider: Literal["mock", "piper"] = "mock"
    tts_voice: str = "en_US-ljspeech-medium"
    tts_model_dir: Path = Path.home() / ".cache/piper"
    max_upload_mb: int = 10

    # Auth: opaque session tokens (DB stores only their SHA-256), sent as an httpOnly cookie
    # (web) or "Authorization: Bearer" (API clients). Set cookie_secure=true behind HTTPS.
    session_days: int = 30
    cookie_secure: bool = False
    # Dev/test escape hatch: trust an X-Learner-Id header without a session. Never in prod.
    allow_learner_header: bool = False

    # Question bank: import content/bank into the database when the API starts, if the bank
    # files changed since the last import (runs in the background; the API serves meanwhile).
    bank_auto_import: bool = True

    # Feature flags. Off -> the feature's endpoints return 404 and the web app hides it.
    feature_ai_monkey: bool = True

    job_workers: int = 2
    daily_new_cards: int = 10
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    log_json: bool = False

    @field_validator(
        "ollama_model",
        "llm_temperature",
        "llm_max_output_tokens",
        "llm_fallback_model",
        mode="before",
    )
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        # docker compose passes unset optional variables as "" (e.g. ${LLM_FALLBACK_MODEL:-})
        return None if isinstance(value, str) and not value.strip() else value
