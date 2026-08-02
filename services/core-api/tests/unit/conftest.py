"""Unit test configuration — no database or network dependencies.

Provides fixtures for isolated unit testing:
- mock_settings: Settings object with safe test values (no real DB connection)
- mock_session: AsyncMock of SQLAlchemy AsyncSession
- mock_db_engine: Mock DatabaseEngine with controllable readiness state
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.db.engine import DatabaseEngine

# ─── Constants ───────────────────────────────────────────────────────────────

_TEST_DB_URL = "postgresql+asyncpg://test:test@localhost:5432/test_unit"


# ─── Settings Fixture ────────────────────────────────────────────────────────


@pytest.fixture
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Provide a Settings instance with safe test defaults.

    Uses monkeypatch to inject environment variables so that Settings
    can be constructed without a .env file or real database URL.
    No actual database connection is made.
    """
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", _TEST_DB_URL)
    monkeypatch.setenv("TEST_DATABASE_URL", _TEST_DB_URL)
    monkeypatch.setenv("FAKE_AUTH_ENABLED", "true")
    monkeypatch.setenv("DATABASE_PASSWORD", "test_password")

    return Settings(_env_file=None)


# ─── Session Fixture ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide an AsyncMock of SQLAlchemy AsyncSession.

    Useful for repository and service tests that require a session
    without touching a real database. Supports async context manager
    protocol and common session methods (execute, commit, rollback, etc.).
    """
    session = AsyncMock(spec_set=["execute", "commit", "rollback", "close", "flush", "get"])
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.get = AsyncMock()
    return session


# ─── DatabaseEngine Fixture ──────────────────────────────────────────────────


@pytest.fixture
def mock_db_engine() -> MagicMock:
    """Provide a MagicMock of DatabaseEngine with controllable state.

    The mock starts in a "ready" state by default. Tests can set
    ``mock_db_engine.is_ready = False`` to simulate degraded mode.

    The session_factory returns an async context manager that yields
    a mock session (AsyncMock).
    """
    engine = MagicMock(spec=DatabaseEngine)

    # Default to ready state
    engine.is_ready = True

    # Mock session factory returning an async context manager
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = mock_session
    session_cm.__aexit__.return_value = False
    engine.session_factory.return_value = session_cm

    # Mock async methods
    engine.check_connectivity = AsyncMock(return_value=True)
    engine.recover_connectivity = AsyncMock(return_value=True)
    engine.dispose = AsyncMock()

    return engine
