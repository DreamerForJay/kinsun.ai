"""Unit tests for app.db.engine — DatabaseEngine."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.engine import DatabaseEngine

# ─── Helpers ─────────────────────────────────────────────────────────────────

_VALID_DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/testdb"


def _make_settings(**overrides: str) -> Settings:
    """Create Settings with environment variable overrides (no .env file)."""
    env = {
        "APP_ENV": "development",
        "DATABASE_URL": _VALID_DB_URL,
    }
    env.update(overrides)
    with patch.dict(os.environ, env, clear=False):
        return Settings(_env_file=None)


# ─── Engine creation ─────────────────────────────────────────────────────────


class TestEngineCreation:
    def test_creates_engine_with_settings(self) -> None:
        """Engine is created from settings with correct pool parameters."""
        settings = _make_settings(DB_POOL_SIZE="3", DB_MAX_OVERFLOW="7")
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            db_engine = DatabaseEngine(settings)

            mock_create.assert_called_once_with(
                _VALID_DB_URL,
                connect_args={"timeout": 5.0},
                pool_size=3,
                max_overflow=7,
                echo=True,  # development mode
            )
            assert db_engine.engine is mock_create.return_value

    def test_null_pool_omits_queue_pool_arguments(self) -> None:
        """NullPool must not receive QueuePool-only sizing arguments."""
        settings = _make_settings(
            DB_POOL_MODE="null",
            DB_POOL_SIZE="3",
            DB_MAX_OVERFLOW="7",
            DB_CONNECT_TIMEOUT_SECONDS="2.5",
        )
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()

            DatabaseEngine(settings)

            mock_create.assert_called_once_with(
                _VALID_DB_URL,
                connect_args={"timeout": 2.5},
                echo=True,
                poolclass=NullPool,
            )
            _, kwargs = mock_create.call_args
            assert "pool_size" not in kwargs
            assert "max_overflow" not in kwargs

    def test_echo_disabled_in_production(self) -> None:
        """Engine echo is False when app_env is production."""
        settings = _make_settings(APP_ENV="production")
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            DatabaseEngine(settings)

            _, kwargs = mock_create.call_args
            assert kwargs["echo"] is False

    def test_echo_enabled_in_development(self) -> None:
        """Engine echo is True when app_env is development."""
        settings = _make_settings(APP_ENV="development")
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            DatabaseEngine(settings)

            _, kwargs = mock_create.call_args
            assert kwargs["echo"] is True

    def test_session_factory_created(self) -> None:
        """Session factory is created with expire_on_commit=False."""
        settings = _make_settings()
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            db_engine = DatabaseEngine(settings)

            assert db_engine.session_factory is not None


# ─── Readiness state ─────────────────────────────────────────────────────────


class TestReadinessState:
    def test_initially_not_ready(self) -> None:
        """Engine starts in not-ready state before connectivity check."""
        settings = _make_settings()
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            db_engine = DatabaseEngine(settings)
            assert db_engine.is_ready is False

    @pytest.mark.asyncio
    async def test_ready_after_successful_connectivity_check(self) -> None:
        """is_ready becomes True after successful check_connectivity."""
        settings = _make_settings()
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_engine = MagicMock()
            mock_conn = AsyncMock()
            # Create a proper async context manager
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_conn
            mock_cm.__aexit__.return_value = False
            mock_engine.connect.return_value = mock_cm
            mock_create.return_value = mock_engine

            db_engine = DatabaseEngine(settings)
            result = await db_engine.check_connectivity()

            assert result is True
            assert db_engine.is_ready is True

    @pytest.mark.asyncio
    async def test_not_ready_after_failed_connectivity_check(self) -> None:
        """is_ready becomes False after failed check_connectivity."""
        settings = _make_settings()
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_engine = MagicMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__.side_effect = ConnectionRefusedError("DB down")
            mock_engine.connect.return_value = mock_cm
            mock_create.return_value = mock_engine

            db_engine = DatabaseEngine(settings)
            result = await db_engine.check_connectivity()

            assert result is False
            assert db_engine.is_ready is False

    @pytest.mark.asyncio
    async def test_ready_transitions_to_not_ready_on_failure(self) -> None:
        """is_ready transitions from True to False when connectivity fails."""
        settings = _make_settings()
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_engine = MagicMock()
            mock_conn = AsyncMock()

            # First call succeeds
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_conn
            mock_cm.__aexit__.return_value = False
            mock_engine.connect.return_value = mock_cm
            mock_create.return_value = mock_engine

            db_engine = DatabaseEngine(settings)
            await db_engine.check_connectivity()
            assert db_engine.is_ready is True

            # Second call fails
            mock_cm_fail = AsyncMock()
            mock_cm_fail.__aenter__.side_effect = ConnectionRefusedError("DB down")
            mock_engine.connect.return_value = mock_cm_fail
            await db_engine.check_connectivity()
            assert db_engine.is_ready is False


class TestConnectivityRecovery:
    @pytest.mark.asyncio
    async def test_concurrent_recovery_calls_share_one_check(self) -> None:
        settings = _make_settings()
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            db_engine = DatabaseEngine(settings)

        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_success() -> bool:
            started.set()
            await release.wait()
            db_engine._ready = True
            return True

        check = AsyncMock(side_effect=delayed_success)
        with patch.object(db_engine, "check_connectivity", check):
            recoveries = [asyncio.create_task(db_engine.recover_connectivity()) for _ in range(8)]
            await started.wait()
            await asyncio.sleep(0)
            release.set()
            results = await asyncio.gather(*recoveries)

        assert results == [True] * 8
        check.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_recovery_can_be_retried_by_later_request(self) -> None:
        settings = _make_settings()
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            db_engine = DatabaseEngine(settings)

        check = AsyncMock(side_effect=[False, True])
        with patch.object(db_engine, "check_connectivity", check):
            assert await db_engine.recover_connectivity() is False
            assert await db_engine.recover_connectivity() is True

        assert check.await_count == 2

    @pytest.mark.asyncio
    async def test_recovery_is_bounded_by_configured_timeout(self) -> None:
        settings = _make_settings(DB_RECOVERY_TIMEOUT_SECONDS="0.01")
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            db_engine = DatabaseEngine(settings)

        async def never_completes() -> bool:
            await asyncio.sleep(60)
            return True

        with patch.object(db_engine, "check_connectivity", side_effect=never_completes):
            assert await db_engine.recover_connectivity() is False

        assert db_engine.is_ready is False


# ─── Dispose ─────────────────────────────────────────────────────────────────


class TestDispose:
    @pytest.mark.asyncio
    async def test_dispose_calls_engine_dispose(self) -> None:
        """dispose() calls the underlying engine dispose."""
        settings = _make_settings()
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_engine = AsyncMock()
            mock_create.return_value = mock_engine

            db_engine = DatabaseEngine(settings)
            db_engine._ready = True
            await db_engine.dispose()

            mock_engine.dispose.assert_awaited_once()
            assert db_engine.is_ready is False

    @pytest.mark.asyncio
    async def test_dispose_handles_timeout(self) -> None:
        """dispose() handles timeout gracefully without raising."""
        settings = _make_settings()
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_engine = AsyncMock()

            async def slow_dispose() -> None:
                await asyncio.sleep(10)

            mock_engine.dispose = slow_dispose
            mock_create.return_value = mock_engine

            db_engine = DatabaseEngine(settings)
            db_engine._ready = True
            # Use very short timeout to trigger TimeoutError
            await db_engine.dispose(timeout=0.01)

            assert db_engine.is_ready is False

    @pytest.mark.asyncio
    async def test_dispose_handles_exception(self) -> None:
        """dispose() handles exceptions gracefully without raising."""
        settings = _make_settings()
        with patch("app.db.engine.create_async_engine") as mock_create:
            mock_engine = AsyncMock()
            mock_engine.dispose.side_effect = RuntimeError("disposal error")
            mock_create.return_value = mock_engine

            db_engine = DatabaseEngine(settings)
            db_engine._ready = True
            # Should not raise
            await db_engine.dispose()

            assert db_engine.is_ready is False
