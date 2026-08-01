"""Unit tests for IdentityService — mode/role validation, dispatch, pagination.

Tests cover:
- get_actor_profile returns correct profile with care_unit_ids
- get_authorized_elders mode/role compatibility validation
- Dispatch to correct repository by mode
- Cursor-based pagination logic
- ADMIN always denied
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AuthorizationDeniedError
from app.middleware.auth import ActorContext
from app.models.enums import ActorType
from app.policies import RoleModeIncompatibleError
from app.repositories.care_relationship_repo import AuthorizedElderRow
from app.services.identity_service import (
    ActorProfile,
    IdentityService,
    decode_cursor,
    encode_cursor,
)

# --- Fixtures ---


@pytest.fixture
def actor_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_active_by_id = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def tenant_membership_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_active_membership = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def care_unit_membership_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_care_unit_ids = AsyncMock(return_value=[])
    repo.is_member = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def care_relationship_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_authorized_elders_by_actor = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def care_assignment_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_authorized_elders_by_worker = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(
    actor_repo,
    tenant_membership_repo,
    care_unit_membership_repo,
    care_relationship_repo,
    care_assignment_repo,
) -> IdentityService:
    return IdentityService(
        actor_repo=actor_repo,
        tenant_membership_repo=tenant_membership_repo,
        care_unit_membership_repo=care_unit_membership_repo,
        care_relationship_repo=care_relationship_repo,
        care_assignment_repo=care_assignment_repo,
    )


@pytest.fixture
def now() -> datetime:
    return datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)


def _actor_context(role: str = ActorType.DAYCARE_CARE_WORKER) -> ActorContext:
    return ActorContext(
        actor_id=uuid.uuid4(),
        actor_role=role,
        tenant_id=uuid.uuid4(),
    )


# --- Cursor encoding/decoding tests ---


class TestCursorEncoding:
    def test_round_trip(self):
        name = "Alice"
        eid = uuid.uuid4()
        cursor = encode_cursor(name, eid)
        decoded_name, decoded_id = decode_cursor(cursor)
        assert decoded_name == name
        assert decoded_id == eid

    def test_unicode_name(self):
        name = "王奶奶"
        eid = uuid.uuid4()
        cursor = encode_cursor(name, eid)
        decoded_name, decoded_id = decode_cursor(cursor)
        assert decoded_name == name
        assert decoded_id == eid


# --- Mode/Role Compatibility Tests ---


class TestModeRoleValidation:
    @pytest.mark.asyncio
    async def test_admin_any_mode_raises(self, service, now):
        ctx = _actor_context(ActorType.ADMIN)
        for mode in ["daycare", "home-care", "family"]:
            with pytest.raises(RoleModeIncompatibleError):
                await service.get_authorized_elders(ctx, mode, now)

    @pytest.mark.asyncio
    async def test_daycare_worker_with_homecare_mode_raises(self, service, now):
        ctx = _actor_context(ActorType.DAYCARE_CARE_WORKER)
        with pytest.raises(RoleModeIncompatibleError):
            await service.get_authorized_elders(ctx, "home-care", now)

    @pytest.mark.asyncio
    async def test_homecare_worker_with_daycare_mode_raises(self, service, now):
        ctx = _actor_context(ActorType.HOME_CARE_WORKER)
        with pytest.raises(RoleModeIncompatibleError):
            await service.get_authorized_elders(ctx, "daycare", now)

    @pytest.mark.asyncio
    async def test_family_member_with_daycare_mode_raises(self, service, now):
        ctx = _actor_context(ActorType.FAMILY_MEMBER)
        with pytest.raises(RoleModeIncompatibleError):
            await service.get_authorized_elders(ctx, "daycare", now)

    @pytest.mark.asyncio
    async def test_homecare_worker_with_family_mode_raises(self, service, now):
        ctx = _actor_context(ActorType.HOME_CARE_WORKER)
        with pytest.raises(RoleModeIncompatibleError):
            await service.get_authorized_elders(ctx, "family", now)


# --- get_actor_profile Tests ---


class TestGetActorProfile:
    @pytest.mark.asyncio
    async def test_returns_formal_actor_profile_with_care_units(
        self,
        service,
        actor_repo,
        tenant_membership_repo,
        care_unit_membership_repo,
    ):
        cu_id1 = uuid.uuid4()
        cu_id2 = uuid.uuid4()
        ctx = _actor_context(ActorType.DAYCARE_CARE_WORKER)
        tenant_membership_repo.get_active_membership.return_value = SimpleNamespace(
            role_code=ctx.actor_role
        )
        care_unit_membership_repo.get_care_unit_ids.return_value = [cu_id1, cu_id2]

        actor_repo.get_active_by_id.return_value = SimpleNamespace(
            id=ctx.actor_id,
            actor_type=ctx.actor_role,
            display_name="張照服員",
        )
        current_time = datetime.now(UTC)
        profile = await service.get_actor_profile(ctx, current_time)

        assert isinstance(profile, ActorProfile)
        assert profile.actor_id == ctx.actor_id
        assert profile.actor_type == ctx.actor_role
        assert profile.display_name == "張照服員"
        assert profile.tenant_id == ctx.tenant_id
        assert profile.role == ctx.actor_role
        assert profile.care_unit_ids == [cu_id1, cu_id2]
        tenant_membership_repo.get_active_membership.assert_awaited_once_with(
            actor_id=ctx.actor_id,
            tenant_id=ctx.tenant_id,
            role_code=ctx.actor_role,
            current_time=current_time,
        )
        care_unit_membership_repo.get_care_unit_ids.assert_awaited_once_with(
            actor_id=ctx.actor_id,
            tenant_id=ctx.tenant_id,
            role_code=ctx.actor_role,
            current_time=current_time,
        )
        actor_repo.get_active_by_id.assert_awaited_once_with(ctx.actor_id)

    @pytest.mark.asyncio
    async def test_denies_profile_without_active_tenant_membership(
        self, service, actor_repo, tenant_membership_repo
    ):
        ctx = _actor_context(ActorType.FAMILY_MEMBER)
        tenant_membership_repo.get_active_membership.return_value = None

        with pytest.raises(AuthorizationDeniedError):
            await service.get_actor_profile(ctx, datetime.now(UTC))

        actor_repo.get_active_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_denies_profile_when_formal_role_differs_from_context(
        self, service, actor_repo, tenant_membership_repo
    ):
        ctx = _actor_context(ActorType.FAMILY_MEMBER)
        tenant_membership_repo.get_active_membership.return_value = MagicMock()
        actor_repo.get_active_by_id.return_value = SimpleNamespace(
            id=ctx.actor_id,
            actor_type=ActorType.ADMIN,
            display_name="Mismatch",
        )

        with pytest.raises(AuthorizationDeniedError):
            await service.get_actor_profile(ctx, datetime.now(UTC))


# --- get_authorized_elders Dispatch Tests ---


class TestDispatchByMode:
    @pytest.mark.asyncio
    async def test_daycare_dispatches_to_relationship_repo(
        self,
        service,
        tenant_membership_repo,
        care_unit_membership_repo,
        care_relationship_repo,
        now,
    ):
        ctx = _actor_context(ActorType.DAYCARE_CARE_WORKER)
        # Setup: active membership
        tenant_membership_repo.get_active_membership.return_value = AsyncMock()
        care_unit_membership_repo.get_care_unit_ids.return_value = [uuid.uuid4()]

        await service.get_authorized_elders(ctx, "daycare", now)

        care_relationship_repo.find_authorized_elders_by_actor.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_daycare_without_tenant_membership_raises(
        self, service, tenant_membership_repo, now
    ):
        ctx = _actor_context(ActorType.DAYCARE_CARE_WORKER)
        tenant_membership_repo.get_active_membership.return_value = None

        with pytest.raises(RoleModeIncompatibleError):
            await service.get_authorized_elders(ctx, "daycare", now)

    @pytest.mark.asyncio
    async def test_homecare_dispatches_to_assignment_repo(self, service, care_assignment_repo, now):
        ctx = _actor_context(ActorType.HOME_CARE_WORKER)

        await service.get_authorized_elders(ctx, "home-care", now)

        care_assignment_repo.find_authorized_elders_by_worker.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_family_dispatches_to_relationship_repo(
        self, service, care_relationship_repo, now
    ):
        ctx = _actor_context(ActorType.FAMILY_MEMBER)

        await service.get_authorized_elders(ctx, "family", now)

        care_relationship_repo.find_authorized_elders_by_actor.assert_awaited_once()
        call_args = care_relationship_repo.find_authorized_elders_by_actor.call_args
        assert set(call_args.kwargs["relationship_types"]) == {
            "FAMILY_SHARE",
            "LEGAL_REPRESENTATIVE",
        }

    @pytest.mark.asyncio
    async def test_legal_rep_can_use_family_mode(self, service, care_relationship_repo, now):
        """A legal representative can use family mode.

        There is no LEGAL_REPRESENTATIVE actor type in the baseline — being a
        legal representative is a CareRelationship type held by a
        FAMILY_MEMBER actor. The mode/role compatibility matrix only checks
        actor_type, so this now authenticates as FAMILY_MEMBER; the
        LEGAL_REPRESENTATIVE relationship type is still included in the
        family-mode relationship_types query (see
        test_family_dispatches_to_relationship_repo).
        """
        ctx = _actor_context(ActorType.FAMILY_MEMBER)

        await service.get_authorized_elders(ctx, "family", now)

        care_relationship_repo.find_authorized_elders_by_actor.assert_awaited_once()


# --- Pagination Tests ---


class TestPagination:
    @pytest.mark.asyncio
    async def test_no_cursor_returns_first_page(self, service, care_relationship_repo, now):
        ctx = _actor_context(ActorType.FAMILY_MEMBER)
        elders = [
            AuthorizedElderRow(
                elder_id=uuid.uuid4(), display_name=f"Elder {i}", care_unit_name=None
            )
            for i in range(5)
        ]
        care_relationship_repo.find_authorized_elders_by_actor.return_value = elders

        result = await service.get_authorized_elders(ctx, "family", now, limit=3)

        assert len(result.items) == 3
        assert result.has_more is True
        assert result.next_cursor is not None

    @pytest.mark.asyncio
    async def test_no_more_items(self, service, care_relationship_repo, now):
        ctx = _actor_context(ActorType.FAMILY_MEMBER)
        elders = [
            AuthorizedElderRow(elder_id=uuid.uuid4(), display_name="Elder 1", care_unit_name=None)
        ]
        care_relationship_repo.find_authorized_elders_by_actor.return_value = elders

        result = await service.get_authorized_elders(ctx, "family", now, limit=20)

        assert len(result.items) == 1
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_cursor_filters_correctly(self, service, care_relationship_repo, now):
        ctx = _actor_context(ActorType.FAMILY_MEMBER)
        eid1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
        eid2 = uuid.UUID("00000000-0000-0000-0000-000000000002")
        eid3 = uuid.UUID("00000000-0000-0000-0000-000000000003")
        elders = [
            AuthorizedElderRow(elder_id=eid1, display_name="Alice", care_unit_name=None),
            AuthorizedElderRow(elder_id=eid2, display_name="Bob", care_unit_name=None),
            AuthorizedElderRow(elder_id=eid3, display_name="Carol", care_unit_name=None),
        ]
        care_relationship_repo.find_authorized_elders_by_actor.return_value = elders

        # Cursor after Alice
        cursor = encode_cursor("Alice", eid1)
        result = await service.get_authorized_elders(ctx, "family", now, cursor=cursor, limit=20)

        assert len(result.items) == 2
        assert result.items[0].display_name == "Bob"
        assert result.items[1].display_name == "Carol"
        assert result.has_more is False
