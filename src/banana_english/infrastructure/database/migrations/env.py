"""Alembic environment. Used both by the app at startup (migrate()) and by the CLI:

uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from banana_english.infrastructure.database.tables import Base

config = context.config
target_metadata = Base.metadata


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite needs batch mode for ALTER
        compare_type=True,
        user_module_prefix="banana_english.infrastructure.database.tables.",
        **kwargs,
    )


def run() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:  # called from migrate(): reuse the app's connection
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    url = os.environ.get("BANANA_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    config.set_main_option("sqlalchemy.url", url)
    if context.is_offline_mode():
        _configure(url=url, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as conn:
        _configure(connection=conn)
        with context.begin_transaction():
            context.run_migrations()


run()
