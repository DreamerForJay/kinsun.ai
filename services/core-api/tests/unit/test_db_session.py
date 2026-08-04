"""Unit tests for request-triggered database readiness recovery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import ServiceUnavailableError
from app.db.engine import DatabaseEngine
from app.db.session import get_db_session


def _mock_engine(*, ready: bool, recovered: bool = True) -> tuple[MagicMock, AsyncMock]:
    engine = MagicMock(spec=DatabaseEngine)
    engine.is_ready = ready
    engine.recover_connectivity = AsyncMock(return_value=recovered)

    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = False
    engine.session_factory.return_value = context
    return engine, session


@pytest.mark.asyncio
async def test_not_ready_engine_recovers_before_yielding_session() -> None:
    engine, session = _mock_engine(ready=False, recovered=True)
    dependency = get_db_session(engine)

    assert await anext(dependency) is session
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)

    engine.recover_connectivity.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_recovery_returns_service_unavailable() -> None:
    engine, _ = _mock_engine(ready=False, recovered=False)
    dependency = get_db_session(engine)

    with pytest.raises(ServiceUnavailableError, match="Database is unavailable"):
        await anext(dependency)

    engine.recover_connectivity.assert_awaited_once()
    engine.session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_exception_fails_closed_as_service_unavailable() -> None:
    engine, _ = _mock_engine(ready=False)
    engine.recover_connectivity.side_effect = RuntimeError("synthetic recovery failure")
    dependency = get_db_session(engine)

    with pytest.raises(ServiceUnavailableError, match="Database is unavailable"):
        await anext(dependency)

    engine.session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_ready_engine_does_not_probe_connectivity() -> None:
    engine, session = _mock_engine(ready=True)
    dependency = get_db_session(engine)

    assert await anext(dependency) is session
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)

    engine.recover_connectivity.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalidated_connection_returns_service_unavailable_and_marks_engine() -> None:
    engine, session = _mock_engine(ready=True)
    dependency = get_db_session(engine)
    assert await anext(dependency) is session
    disconnect = DBAPIError(
        "SELECT synthetic",
        {},
        RuntimeError("synthetic connection closed"),
        connection_invalidated=True,
    )

    with pytest.raises(ServiceUnavailableError, match="Database is unavailable"):
        await dependency.athrow(disconnect)

    session.rollback.assert_awaited_once()
    engine.mark_unready.assert_called_once_with()


@pytest.mark.asyncio
async def test_non_disconnect_database_error_is_not_reclassified() -> None:
    engine, session = _mock_engine(ready=True)
    dependency = get_db_session(engine)
    assert await anext(dependency) is session
    database_error = DBAPIError(
        "SELECT synthetic",
        {},
        RuntimeError("synthetic statement failure"),
        connection_invalidated=False,
    )

    with pytest.raises(DBAPIError) as exc_info:
        await dependency.athrow(database_error)

    assert exc_info.value is database_error
    session.rollback.assert_awaited_once()
    engine.mark_unready.assert_not_called()


@pytest.mark.asyncio
async def test_rollback_failure_does_not_hide_invalidated_connection() -> None:
    engine, session = _mock_engine(ready=True)
    session.rollback.side_effect = RuntimeError("synthetic rollback failure")
    dependency = get_db_session(engine)
    assert await anext(dependency) is session
    disconnect = DBAPIError(
        "SELECT synthetic",
        {},
        RuntimeError("synthetic connection closed"),
        connection_invalidated=True,
    )

    with pytest.raises(ServiceUnavailableError, match="Database is unavailable"):
        await dependency.athrow(disconnect)

    engine.mark_unready.assert_called_once_with()
