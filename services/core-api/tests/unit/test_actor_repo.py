"""Unit tests for formal actor identity lookups."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.actor_repo import ActorRepository


@pytest.mark.asyncio
async def test_get_active_by_id_returns_actor() -> None:
    session = AsyncMock()
    expected = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = expected
    session.execute.return_value = result

    actor_id = uuid.uuid4()
    actor = await ActorRepository(session).get_active_by_id(actor_id)

    assert actor is expected
    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
    assert "actor.actor_id" in compiled
    assert "actor.status" in compiled


@pytest.mark.asyncio
async def test_get_active_by_id_returns_none_when_unavailable() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    actor = await ActorRepository(session).get_active_by_id(uuid.uuid4())

    assert actor is None
