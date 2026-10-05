"""Database session management with startup retry."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

def _engine_kwargs() -> dict[str, Any]:
    """Pool sizing only applies to server-side databases.

    SQLite (used by the test suite) uses StaticPool and rejects these options,
    so they are omitted for any sqlite:// URL.
    """
    url = settings.database_url
    if url.startswith("sqlite"):
        return {"pool_pre_ping": False}
    return {
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,
        "pool_timeout": 10,
    }


engine: AsyncEngine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug and settings.is_development,
    **_engine_kwargs(),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def wait_for_database(max_attempts: int = 30, delay: float = 1.0) -> bool:
    """Retry the database connection so startup is resilient to slow PostgreSQL.

    Returns True once connectivity is established. Raises after `max_attempts`.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            if attempt > 1:
                logger.info("database connection established", extra={"attempts": attempt})
            return True
        except Exception as exc:  # noqa: BLE001 — broad on purpose
            last_error = exc
            logger.warning(
                "database not ready yet; retrying",
                extra={"attempt": attempt, "max": max_attempts, "error": str(exc)},
            )
            await asyncio.sleep(delay)

    logger.error(
        "could not connect to the database",
        extra={"error": str(last_error) if last_error else "unknown"},
    )
    raise RuntimeError(
        f"database unreachable after {max_attempts} attempts"
    ) from last_error


@contextlib.asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Context-managed session with automatic rollback on error."""
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session, rolls back on error."""
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def close_engine() -> None:
    await engine.dispose()
