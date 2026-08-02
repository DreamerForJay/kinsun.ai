"""Async SQLAlchemy engine and session factory management.

Manages the database engine lifecycle including connection pooling,
connectivity checks, and graceful shutdown with timeout.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import AppEnv, DatabasePoolMode, Settings

logger = logging.getLogger(__name__)


class DatabaseEngine:
    """Manages async SQLAlchemy engine lifecycle.

    Provides connection pooling, connectivity verification, degraded mode
    tracking, and graceful disposal with a configurable timeout.
    """

    def __init__(self, settings: Settings) -> None:
        engine_options: dict[str, Any] = {
            "connect_args": {"timeout": settings.db_connect_timeout_seconds},
            "echo": settings.app_env == AppEnv.DEVELOPMENT,
        }
        if settings.db_pool_mode == DatabasePoolMode.NULL:
            engine_options["poolclass"] = NullPool
        else:
            engine_options["pool_size"] = settings.db_pool_size
            engine_options["max_overflow"] = settings.db_max_overflow

        self._engine: AsyncEngine = create_async_engine(settings.database_url, **engine_options)
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._ready: bool = False
        self._recovery_timeout_seconds = settings.db_recovery_timeout_seconds
        self._recovery_lock = asyncio.Lock()
        self._recovery_task: asyncio.Task[bool] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Return the underlying async engine."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the session factory for creating request-scoped sessions."""
        return self._session_factory

    @property
    def is_ready(self) -> bool:
        """Return True if the last connectivity check succeeded."""
        return self._ready

    async def check_connectivity(self) -> bool:
        """Execute SELECT 1 to verify database connectivity.

        Updates the internal readiness state based on the result.
        Returns True if connectivity is confirmed, False otherwise.
        """
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            self._ready = True
            return True
        except Exception:
            logger.warning("Database connectivity check failed", exc_info=True)
            self._ready = False
            return False

    async def _bounded_recovery_check(self) -> bool:
        """Run one connectivity check within the configured recovery budget."""
        try:
            return await asyncio.wait_for(
                self.check_connectivity(),
                timeout=self._recovery_timeout_seconds,
            )
        except TimeoutError:
            self._ready = False
            logger.warning(
                "Database connectivity recovery timed out after %.1f seconds",
                self._recovery_timeout_seconds,
            )
            return False

    async def recover_connectivity(self) -> bool:
        """Recover readiness with one bounded check shared by concurrent callers.

        This is request/startup triggered; it does not create a periodic probe.
        A failed completed attempt is cleared so a later request can retry after
        Aurora resumes, while overlapping requests await the same in-flight task.
        """
        if self._ready:
            return True

        async with self._recovery_lock:
            if self._ready:
                return True
            recovery_task = self._recovery_task
            if recovery_task is None:
                recovery_task = asyncio.create_task(self._bounded_recovery_check())
                self._recovery_task = recovery_task

        try:
            return await asyncio.shield(recovery_task)
        finally:
            if recovery_task.done():
                async with self._recovery_lock:
                    if self._recovery_task is recovery_task:
                        self._recovery_task = None

    async def dispose(self, timeout: float = 30.0) -> None:
        """Close all connections and dispose of the engine pool.

        Args:
            timeout: Maximum seconds to wait for disposal. Defaults to 30.
        """
        try:
            await asyncio.wait_for(self._engine.dispose(), timeout=timeout)
            self._ready = False
            logger.info("Database engine disposed successfully")
        except TimeoutError:
            logger.error("Database engine disposal timed out after %.1f seconds", timeout)
            self._ready = False
        except Exception:
            logger.error("Error during database engine disposal", exc_info=True)
            self._ready = False
