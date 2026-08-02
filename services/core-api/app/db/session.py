"""Request-scoped async database session dependency.

Provides a FastAPI dependency that yields one session per request with
auto-commit on success and auto-rollback on exception. Raises
ServiceUnavailableError (503) when the database engine is not ready.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceUnavailableError
from app.db.engine import DatabaseEngine

logger = logging.getLogger(__name__)

# Module-level reference set during application startup.
_db_engine: DatabaseEngine | None = None


def init_db_engine(engine: DatabaseEngine) -> None:
    """Store the DatabaseEngine instance for use by the session dependency.

    Called once during application startup after the engine is created.
    """
    global _db_engine  # noqa: PLW0603
    _db_engine = engine


def get_db_engine() -> DatabaseEngine:
    """Return the module-level DatabaseEngine instance.

    Raises RuntimeError if the engine has not been initialized via
    ``init_db_engine()`` (indicates a startup ordering bug).
    """
    if _db_engine is None:
        raise RuntimeError("DatabaseEngine not initialized. Call init_db_engine() during startup.")
    return _db_engine


async def get_db_session(
    db_engine: DatabaseEngine = Depends(get_db_engine),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async session.

    - If the engine is not ready, performs one bounded single-flight recovery
      check before raising ``ServiceUnavailableError`` (HTTP 503).
    - Auto-commits on success.
    - Auto-rolls back on exception, then re-raises.

    Usage as a FastAPI dependency::

        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_db_session)):
            ...
    """
    if not db_engine.is_ready:
        try:
            recovered = await db_engine.recover_connectivity()
        except Exception:
            # Keep unexpected dependency failures out of request logs; exception
            # values from database libraries can contain connection metadata.
            logger.warning("Database readiness recovery failed")
            recovered = False
        if not recovered:
            raise ServiceUnavailableError("Database is unavailable")

    async with db_engine.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
