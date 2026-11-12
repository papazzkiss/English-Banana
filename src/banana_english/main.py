"""ASGI entry point: `uv run uvicorn banana_english.main:app --reload`."""

import logging
import threading

from banana_english.api.app import create_app
from banana_english.domain.interfaces.tts import TTSError

app = create_app()


def _warm_up_voice() -> None:
    """Download and load AI Monkey's voice now, so the first spoken reply is not slow."""
    try:
        app.state.container.tts.synthesize("Hi!")
    except TTSError as exc:
        logging.getLogger("banana_english").warning("AI Monkey voice unavailable: %s", exc)


if app.state.container.settings.feature_ai_monkey:
    threading.Thread(target=_warm_up_voice, name="tts-warm-up", daemon=True).start()
if app.state.container.settings.llm_warm_up:
    # Load the LLM now (logs llm_ready / llm_unavailable with the model name) so the first
    # learner does not wait for a cold load. Ollama keeps it for BANANA_LLM_KEEP_ALIVE.
    threading.Thread(
        target=app.state.container.llm.warm_up, name="llm-warm-up", daemon=True
    ).start()


def _import_bank() -> None:
    """Load a new or changed question bank into the database (skipped when unchanged)."""
    log = logging.getLogger("banana_english.bank")
    try:
        from sqlalchemy.orm import sessionmaker

        from banana_english.contentbank.importer import import_if_changed
        from banana_english.infrastructure.database.repositories import create_db_engine

        engine = create_db_engine(app.state.container.settings.database_url)
        result = import_if_changed(sessionmaker(engine, expire_on_commit=False), log=log.info)
        log.info("question bank %s", f"imported: {result}" if result else "up to date")
    except Exception:  # the app works without a bank; never crash the API over it
        log.exception("question bank import failed")


if app.state.container.settings.bank_auto_import:
    threading.Thread(target=_import_bank, name="bank-import", daemon=True).start()
