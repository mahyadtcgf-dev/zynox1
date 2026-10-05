"""Alembic environment.

Uses the application's async engine so migrations share one connection pool and
one settings source. The URL is injected from `settings.database_url`.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.models import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    # Alembic's fileConfig() reconfigures the ROOT logger from alembic.ini
    # (level=WARNING, plain stderr handler). When migrations run inside the app
    # lifespan that silently destroys the application's JSON logging: every
    # log after startup is dropped. The app therefore sets
    # ``configure_logger = False`` on the Config it builds; the standalone CLI
    # still gets logging configured as normal.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Import all models so autogenerate sees the full metadata.
import app.models  # noqa: F401, E402

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", settings.async_database_url)


def run_migrations_offline() -> None:
    """Run migrations without a DB connection (emits SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations with an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
