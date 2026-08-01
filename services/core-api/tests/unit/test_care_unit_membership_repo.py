"""Unit tests for CareUnitMembershipRepository.

Tests the repository logic using a mocked async session.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.care_unit_membership_repo import CareUnitMembershipRepository


class TestCareUnitMembershipRepositoryInit:
    """Tests for CareUnitMembershipRepository constructor."""

    def test_accepts_session(self) -> None:
        """Constructor stores the session."""
        session = AsyncMock()
        repo = CareUnitMembershipRepository(session)
        assert repo._session is session


class TestIsMember:
    """Tests for CareUnitMembershipRepository.is_member."""

    @pytest.mark.asyncio
    async def test_returns_true_when_active_membership_exists(self) -> None:
        """Returns True when an active membership record is found."""
        session = AsyncMock()
        repo = CareUnitMembershipRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        session.execute.return_value = mock_result

        actor_id = uuid.uuid4()
        care_unit_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        current_time = datetime.now(UTC)

        result = await repo.is_member(
            actor_id, care_unit_id, tenant_id, "DAYCARE_CARE_WORKER", current_time
        )

        assert result is True
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_no_membership(self) -> None:
        """Returns False when no active membership exists."""
        session = AsyncMock()
        repo = CareUnitMembershipRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        actor_id = uuid.uuid4()
        care_unit_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        current_time = datetime.now(UTC)

        result = await repo.is_member(
            actor_id, care_unit_id, tenant_id, "DAYCARE_CARE_WORKER", current_time
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_query_includes_actor_id_and_care_unit_id(self) -> None:
        """Verifies query filters on actor_id, care_unit_id, tenant_id, and status."""
        session = AsyncMock()
        repo = CareUnitMembershipRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        actor_id = uuid.uuid4()
        care_unit_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        current_time = datetime.now(UTC)

        await repo.is_member(actor_id, care_unit_id, tenant_id, "DAYCARE_CARE_WORKER", current_time)

        session.execute.assert_called_once()
        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "actor_tenant_membership" in compiled
        assert "actor_id" in compiled
        assert "care_unit_id" in compiled
        assert "tenant_id" in compiled
        assert "role_code" in compiled
        assert "status" in compiled
        assert "effective_from" in compiled
        assert "effective_to" in compiled


class TestGetCareUnitIds:
    """Tests for CareUnitMembershipRepository.get_care_unit_ids."""

    @pytest.mark.asyncio
    async def test_returns_list_of_care_unit_ids(self) -> None:
        """Returns list of UUIDs for active memberships."""
        session = AsyncMock()
        repo = CareUnitMembershipRepository(session)

        cu_id_1 = uuid.uuid4()
        cu_id_2 = uuid.uuid4()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [cu_id_1, cu_id_2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        current_time = datetime.now(UTC)

        result = await repo.get_care_unit_ids(
            actor_id, tenant_id, "DAYCARE_CARE_WORKER", current_time
        )

        assert result == [cu_id_1, cu_id_2]
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_memberships(self) -> None:
        """Returns empty list when no active memberships exist."""
        session = AsyncMock()
        repo = CareUnitMembershipRepository(session)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        current_time = datetime.now(UTC)

        result = await repo.get_care_unit_ids(
            actor_id, tenant_id, "DAYCARE_CARE_WORKER", current_time
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_query_includes_actor_id_and_tenant_id(self) -> None:
        """Verifies query filters on actor_id, tenant_id, and status."""
        session = AsyncMock()
        repo = CareUnitMembershipRepository(session)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        current_time = datetime.now(UTC)

        await repo.get_care_unit_ids(actor_id, tenant_id, "DAYCARE_CARE_WORKER", current_time)

        session.execute.assert_called_once()
        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "actor_tenant_membership" in compiled
        assert "actor_id" in compiled
        assert "tenant_id" in compiled
        assert "role_code" in compiled
        assert "status" in compiled
        assert "effective_from" in compiled
        assert "effective_to" in compiled
