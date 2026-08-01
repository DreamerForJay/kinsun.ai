"""Integration tests for CareRelationship and CareAssignment repositories.

Tests actual SQL queries against a real PostgreSQL database via Docker.
Validates:
- CareRelationshipRepository.find_valid_for_actor
- CareAssignmentRepository.find_valid_for_worker
- Authorized-elders queries (daycare, home-care, family modes)
- Tenant isolation (cross-tenant data invisible)

Requirements: 9.2, 9.4, 10.6, 10.7, 10.8
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio

from app.models.actor import Actor
from app.models.care_assignment import CareAssignment
from app.models.care_relationship import CareRelationship
from app.models.care_unit import CareUnit
from app.models.elder import Elder
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant
from app.repositories.care_assignment_repo import CareAssignmentRepository
from app.repositories.care_relationship_repo import CareRelationshipRepository
from app.repositories.care_unit_membership_repo import CareUnitMembershipRepository
from app.repositories.tenant_membership_repo import TenantMembershipRepository

# ─── Helper: fixed time ──────────────────────────────────────────────────────

NOW = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(loop_scope="function")
async def seed_data(db_session):
    """Seed the database with test data for repository integration tests.

    Creates two tenants (A and B), actors, elders, care units,
    memberships, relationships and assignments.

    None of the models declare an ORM `relationship()` (see app/models/*.py —
    plain `mapped_column(..., ForeignKey(...))`), so SQLAlchemy's unit-of-work
    cannot infer flush order from FK columns alone. With real foreign keys now
    enforced by the baseline schema, rows must be flushed in dependency order
    explicitly: Tenant/Actor first, then CareUnit/Elder (depend on Tenant),
    then memberships/relationships/assignments (depend on all of the above).
    """
    # Tenants
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()
    tenant_a = Tenant(id=tenant_a_id, name="Tenant A", tenant_type="CARE_ORGANIZATION")
    tenant_b = Tenant(id=tenant_b_id, name="Tenant B", tenant_type="HOME_CARE_PROVIDER")
    db_session.add_all([tenant_a, tenant_b])

    # Actors
    worker_id = uuid.uuid4()
    daycare_worker_id = uuid.uuid4()
    family_member_id = uuid.uuid4()
    legal_rep_id = uuid.uuid4()
    other_worker_id = uuid.uuid4()

    worker = Actor(id=worker_id, actor_type="HOME_CARE_WORKER", display_name="Worker A")
    daycare_worker = Actor(
        id=daycare_worker_id, actor_type="DAYCARE_CARE_WORKER", display_name="DC Worker"
    )
    family_member = Actor(id=family_member_id, actor_type="FAMILY_MEMBER", display_name="Family A")
    # There is no LEGAL_REPRESENTATIVE actor type in the baseline — being a legal
    # representative is a CareRelationship type (see app/models/enums.py), so this
    # actor authenticates as FAMILY_MEMBER and holds a LEGAL_REPRESENTATIVE
    # relationship below.
    legal_rep = Actor(id=legal_rep_id, actor_type="FAMILY_MEMBER", display_name="Legal Rep")
    other_worker = Actor(id=other_worker_id, actor_type="HOME_CARE_WORKER", display_name="Worker B")
    db_session.add_all([worker, daycare_worker, family_member, legal_rep, other_worker])
    await db_session.flush()

    # Care Units
    care_unit_a_id = uuid.uuid4()
    care_unit_b_id = uuid.uuid4()

    care_unit_a = CareUnit(
        id=care_unit_a_id, tenant_id=tenant_a_id, unit_type="DAYCARE_CENTER", name="Unit A"
    )
    care_unit_b = CareUnit(
        id=care_unit_b_id, tenant_id=tenant_b_id, unit_type="HOME_CARE_AGENCY", name="Unit B"
    )
    db_session.add_all([care_unit_a, care_unit_b])
    await db_session.flush()

    # Elders
    elder_1_id = uuid.uuid4()
    elder_2_id = uuid.uuid4()
    elder_3_id = uuid.uuid4()  # In tenant B

    elder_1 = Elder(
        id=elder_1_id,
        tenant_id=tenant_a_id,
        display_name="Elder One",
        primary_care_setting="DAYCARE",
    )
    elder_2 = Elder(
        id=elder_2_id,
        tenant_id=tenant_a_id,
        display_name="Elder Two",
        primary_care_setting="DAYCARE",
    )
    elder_3 = Elder(
        id=elder_3_id,
        tenant_id=tenant_b_id,
        display_name="Elder Three",
        primary_care_setting="HOME_CARE",
    )
    db_session.add_all([elder_1, elder_2, elder_3])
    await db_session.flush()

    # actor_tenant_membership rows (TenantMembership + CareUnitMembership merged
    # into ActorTenantMembership — see app/models/membership.py). Giving the
    # daycare worker's row a care_unit_id makes it count as both a tenant
    # membership (TenantMembershipRepository does not filter on care_unit_id)
    # and a care-unit membership.
    tm_daycare = ActorTenantMembership(
        actor_id=daycare_worker_id,
        tenant_id=tenant_a_id,
        care_unit_id=care_unit_a_id,
        role_code="DAYCARE_CARE_WORKER",
        effective_from=NOW - timedelta(days=30),
        effective_to=NOW + timedelta(days=1),
    )
    tm_worker = ActorTenantMembership(
        actor_id=worker_id,
        tenant_id=tenant_a_id,
        care_unit_id=None,
        role_code="HOME_CARE_WORKER",
        effective_from=NOW - timedelta(days=30),
        effective_to=NOW + timedelta(days=1),
    )
    db_session.add_all([tm_daycare, tm_worker])
    await db_session.flush()

    # CareRelationships
    # 1) Active DAYCARE_ASSIGNMENT for daycare_worker -> elder_1
    cr_daycare = CareRelationship(
        elder_id=elder_1_id,
        actor_id=daycare_worker_id,
        tenant_id=tenant_a_id,
        care_unit_id=care_unit_a_id,
        relationship_type="DAYCARE_ASSIGNMENT",
        scope=["elder:basic:read", "elder:access_context:read"],
        status="ACTIVE",
        effective_from=NOW - timedelta(days=30),
        effective_to=None,
    )
    # 2) Active FAMILY_SHARE for family_member -> elder_1
    cr_family = CareRelationship(
        elder_id=elder_1_id,
        actor_id=family_member_id,
        tenant_id=tenant_a_id,
        care_unit_id=None,
        relationship_type="FAMILY_SHARE",
        scope=["elder:basic:read"],
        status="ACTIVE",
        effective_from=NOW - timedelta(days=60),
        effective_to=None,
    )
    # 3) Active LEGAL_REPRESENTATIVE for legal_rep -> elder_2
    cr_legal = CareRelationship(
        elder_id=elder_2_id,
        actor_id=legal_rep_id,
        tenant_id=tenant_a_id,
        care_unit_id=None,
        relationship_type="LEGAL_REPRESENTATIVE",
        scope=["elder:basic:read", "elder:sensitive:read"],
        status="ACTIVE",
        effective_from=NOW - timedelta(days=90),
        effective_to=NOW + timedelta(days=365),
    )
    # 4) Expired relationship (should NOT appear in queries)
    cr_expired = CareRelationship(
        elder_id=elder_1_id,
        actor_id=legal_rep_id,
        tenant_id=tenant_a_id,
        care_unit_id=None,
        relationship_type="FAMILY_SHARE",
        scope=["elder:basic:read"],
        status="ACTIVE",
        effective_from=NOW - timedelta(days=365),
        effective_to=NOW - timedelta(days=1),  # expired yesterday
    )
    # 5) INACTIVE relationship (should NOT appear in queries)
    cr_inactive = CareRelationship(
        elder_id=elder_2_id,
        actor_id=family_member_id,
        tenant_id=tenant_a_id,
        care_unit_id=None,
        relationship_type="FAMILY_SHARE",
        scope=["elder:basic:read"],
        status="INACTIVE",
        effective_from=NOW - timedelta(days=30),
        effective_to=None,
    )
    # 6) Relationship in tenant B (for isolation tests)
    cr_tenant_b = CareRelationship(
        elder_id=elder_3_id,
        actor_id=family_member_id,
        tenant_id=tenant_b_id,
        care_unit_id=None,
        relationship_type="FAMILY_SHARE",
        scope=["elder:basic:read"],
        status="ACTIVE",
        effective_from=NOW - timedelta(days=30),
        effective_to=None,
    )
    db_session.add_all([cr_daycare, cr_family, cr_legal, cr_expired, cr_inactive, cr_tenant_b])
    await db_session.flush()

    # CareAssignments
    # 1) Active CONFIRMED assignment for worker -> elder_1
    ca_active = CareAssignment(
        care_unit_id=care_unit_a_id,
        elder_id=elder_1_id,
        worker_id=worker_id,
        tenant_id=tenant_a_id,
        service_start=NOW - timedelta(hours=2),
        service_end=NOW + timedelta(hours=6),
        service_scope=["elder:basic:read", "elder:access_context:read"],
        status="CONFIRMED",
    )
    # 2) IN_PROGRESS assignment for worker -> elder_2
    ca_in_progress = CareAssignment(
        care_unit_id=care_unit_a_id,
        elder_id=elder_2_id,
        worker_id=worker_id,
        tenant_id=tenant_a_id,
        service_start=NOW - timedelta(hours=1),
        service_end=NOW + timedelta(hours=3),
        service_scope=["elder:basic:read"],
        status="IN_PROGRESS",
    )
    # 3) DRAFT assignment (should NOT appear — wrong status; the baseline has no
    #    SCHEDULED status, a newly created assignment starts as DRAFT)
    ca_draft = CareAssignment(
        care_unit_id=care_unit_a_id,
        elder_id=elder_1_id,
        worker_id=other_worker_id,
        tenant_id=tenant_a_id,
        service_start=NOW + timedelta(hours=1),
        service_end=NOW + timedelta(hours=5),
        service_scope=["elder:basic:read"],
        status="DRAFT",
    )
    # 4) Expired assignment (should NOT appear — outside time window)
    ca_expired = CareAssignment(
        care_unit_id=care_unit_a_id,
        elder_id=elder_1_id,
        worker_id=worker_id,
        tenant_id=tenant_a_id,
        service_start=NOW - timedelta(hours=10),
        service_end=NOW - timedelta(hours=2),
        service_scope=["elder:basic:read"],
        status="CONFIRMED",
    )
    # 5) Assignment in tenant B (for isolation tests)
    ca_tenant_b = CareAssignment(
        care_unit_id=care_unit_b_id,
        elder_id=elder_3_id,
        worker_id=worker_id,
        tenant_id=tenant_b_id,
        service_start=NOW - timedelta(hours=1),
        service_end=NOW + timedelta(hours=5),
        service_scope=["elder:basic:read"],
        status="CONFIRMED",
    )
    db_session.add_all([ca_active, ca_in_progress, ca_draft, ca_expired, ca_tenant_b])

    await db_session.flush()

    return {
        "tenant_a_id": tenant_a_id,
        "tenant_b_id": tenant_b_id,
        "worker_id": worker_id,
        "daycare_worker_id": daycare_worker_id,
        "family_member_id": family_member_id,
        "legal_rep_id": legal_rep_id,
        "other_worker_id": other_worker_id,
        "elder_1_id": elder_1_id,
        "elder_2_id": elder_2_id,
        "elder_3_id": elder_3_id,
        "care_unit_a_id": care_unit_a_id,
        "care_unit_b_id": care_unit_b_id,
    }


# ─── Membership Repository Tests ─────────────────────────────────────────────


class TestMembershipEffectiveWindows:
    """Membership access must respect role and both time boundaries."""

    async def test_tenant_membership_respects_role_and_effective_window(
        self, db_session, seed_data
    ):
        repo = TenantMembershipRepository(db_session)
        actor_id = seed_data["daycare_worker_id"]
        tenant_id = seed_data["tenant_a_id"]
        role_code = "DAYCARE_CARE_WORKER"

        assert await repo.get_active_membership(actor_id, tenant_id, role_code, NOW) is not None
        assert (
            await repo.get_active_membership(actor_id, tenant_id, "HOME_CARE_WORKER", NOW) is None
        )
        assert (
            await repo.get_active_membership(
                actor_id,
                tenant_id,
                role_code,
                NOW - timedelta(days=60),
            )
            is None
        )
        assert (
            await repo.get_active_membership(
                actor_id,
                tenant_id,
                role_code,
                NOW + timedelta(days=1),
            )
            is None
        )

    async def test_care_unit_membership_respects_role_and_effective_window(
        self, db_session, seed_data
    ):
        repo = CareUnitMembershipRepository(db_session)
        actor_id = seed_data["daycare_worker_id"]
        tenant_id = seed_data["tenant_a_id"]
        care_unit_id = seed_data["care_unit_a_id"]
        role_code = "DAYCARE_CARE_WORKER"

        assert await repo.is_member(actor_id, care_unit_id, tenant_id, role_code, NOW) is True
        assert await repo.get_care_unit_ids(actor_id, tenant_id, role_code, NOW) == [care_unit_id]
        assert (
            await repo.is_member(
                actor_id,
                care_unit_id,
                tenant_id,
                "HOME_CARE_WORKER",
                NOW,
            )
            is False
        )
        assert await repo.get_care_unit_ids(actor_id, tenant_id, "HOME_CARE_WORKER", NOW) == []
        assert (
            await repo.is_member(
                actor_id,
                care_unit_id,
                tenant_id,
                role_code,
                NOW - timedelta(days=60),
            )
            is False
        )
        assert (
            await repo.get_care_unit_ids(
                actor_id,
                tenant_id,
                role_code,
                NOW + timedelta(days=1),
            )
            == []
        )


# ─── CareRelationshipRepository Tests ────────────────────────────────────────


class TestCareRelationshipFindValidForActor:
    """Tests for CareRelationshipRepository.find_valid_for_actor."""

    async def test_finds_active_relationship(self, db_session, seed_data):
        """Active DAYCARE_ASSIGNMENT relationship is found."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        result = await repo.find_valid_for_actor(
            actor_id=seed_data["daycare_worker_id"],
            elder_id=seed_data["elder_1_id"],
            relationship_type="DAYCARE_ASSIGNMENT",
            current_time=NOW,
        )
        assert result is not None
        assert result.actor_id == seed_data["daycare_worker_id"]
        assert result.elder_id == seed_data["elder_1_id"]
        assert result.status == "ACTIVE"
        assert result.relationship_type == "DAYCARE_ASSIGNMENT"

    async def test_finds_family_share_relationship(self, db_session, seed_data):
        """Active FAMILY_SHARE relationship is found."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        result = await repo.find_valid_for_actor(
            actor_id=seed_data["family_member_id"],
            elder_id=seed_data["elder_1_id"],
            relationship_type="FAMILY_SHARE",
            current_time=NOW,
        )
        assert result is not None
        assert result.relationship_type == "FAMILY_SHARE"

    async def test_returns_none_for_expired_relationship(self, db_session, seed_data):
        """Expired relationship (current_time >= effective_to) returns None."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        result = await repo.find_valid_for_actor(
            actor_id=seed_data["legal_rep_id"],
            elder_id=seed_data["elder_1_id"],
            relationship_type="FAMILY_SHARE",
            current_time=NOW,
        )
        assert result is None

    async def test_returns_none_for_inactive_relationship(self, db_session, seed_data):
        """INACTIVE relationship returns None."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        result = await repo.find_valid_for_actor(
            actor_id=seed_data["family_member_id"],
            elder_id=seed_data["elder_2_id"],
            relationship_type="FAMILY_SHARE",
            current_time=NOW,
        )
        assert result is None

    async def test_returns_none_for_wrong_relationship_type(self, db_session, seed_data):
        """Wrong relationship_type returns None."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        result = await repo.find_valid_for_actor(
            actor_id=seed_data["daycare_worker_id"],
            elder_id=seed_data["elder_1_id"],
            relationship_type="FAMILY_SHARE",
            current_time=NOW,
        )
        assert result is None

    async def test_returns_none_for_not_yet_effective(self, db_session, seed_data):
        """Relationship with effective_from in the future returns None."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        # Query at a time before the daycare relationship's effective_from
        past_time = NOW - timedelta(days=60)
        result = await repo.find_valid_for_actor(
            actor_id=seed_data["daycare_worker_id"],
            elder_id=seed_data["elder_1_id"],
            relationship_type="DAYCARE_ASSIGNMENT",
            current_time=past_time,
        )
        assert result is None

    async def test_returns_none_for_wrong_actor(self, db_session, seed_data):
        """Querying with wrong actor_id returns None."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        result = await repo.find_valid_for_actor(
            actor_id=seed_data["worker_id"],  # Not the daycare worker
            elder_id=seed_data["elder_1_id"],
            relationship_type="DAYCARE_ASSIGNMENT",
            current_time=NOW,
        )
        assert result is None


class TestCareRelationshipAuthorizedElders:
    """Tests for CareRelationshipRepository.find_authorized_elders_by_actor."""

    async def test_daycare_mode_returns_elders(self, db_session, seed_data):
        """Daycare mode returns elders with active DAYCARE_ASSIGNMENT."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        results = await repo.find_authorized_elders_by_actor(
            actor_id=seed_data["daycare_worker_id"],
            relationship_types=["DAYCARE_ASSIGNMENT"],
            current_time=NOW,
        )
        assert len(results) == 1
        assert results[0].elder_id == seed_data["elder_1_id"]
        assert results[0].display_name == "Elder One"
        assert results[0].care_unit_name == "Unit A"

    async def test_family_mode_returns_elders(self, db_session, seed_data):
        """Family mode returns elders with FAMILY_SHARE or LEGAL_REPRESENTATIVE."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        results = await repo.find_authorized_elders_by_actor(
            actor_id=seed_data["family_member_id"],
            relationship_types=["FAMILY_SHARE", "LEGAL_REPRESENTATIVE"],
            current_time=NOW,
        )
        # family_member has active FAMILY_SHARE to elder_1 only
        # (elder_2 is INACTIVE status)
        assert len(results) == 1
        assert results[0].elder_id == seed_data["elder_1_id"]

    async def test_legal_rep_family_mode(self, db_session, seed_data):
        """Legal rep querying with family mode relationship types."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        results = await repo.find_authorized_elders_by_actor(
            actor_id=seed_data["legal_rep_id"],
            relationship_types=["FAMILY_SHARE", "LEGAL_REPRESENTATIVE"],
            current_time=NOW,
        )
        # legal_rep has LEGAL_REPRESENTATIVE to elder_2 (active, within time)
        # and an expired FAMILY_SHARE to elder_1 (should NOT appear)
        assert len(results) == 1
        assert results[0].elder_id == seed_data["elder_2_id"]
        assert results[0].display_name == "Elder Two"

    async def test_excludes_expired_from_results(self, db_session, seed_data):
        """Expired relationships do not appear in authorized-elders listing."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        # legal_rep's FAMILY_SHARE to elder_1 is expired
        results = await repo.find_authorized_elders_by_actor(
            actor_id=seed_data["legal_rep_id"],
            relationship_types=["FAMILY_SHARE"],
            current_time=NOW,
        )
        elder_ids = [r.elder_id for r in results]
        assert seed_data["elder_1_id"] not in elder_ids

    async def test_care_unit_filter(self, db_session, seed_data):
        """Filtering by care_unit_ids restricts results correctly."""
        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        # Filter to care_unit_a — should still find daycare worker's elder
        results = await repo.find_authorized_elders_by_actor(
            actor_id=seed_data["daycare_worker_id"],
            relationship_types=["DAYCARE_ASSIGNMENT"],
            current_time=NOW,
            care_unit_ids=[seed_data["care_unit_a_id"]],
        )
        assert len(results) == 1

        # Filter to a non-existent care unit — no results
        results = await repo.find_authorized_elders_by_actor(
            actor_id=seed_data["daycare_worker_id"],
            relationship_types=["DAYCARE_ASSIGNMENT"],
            current_time=NOW,
            care_unit_ids=[uuid.uuid4()],
        )
        assert len(results) == 0

    async def test_results_ordered_by_display_name(self, db_session, seed_data):
        """Results are ordered by display_name, then elder_id."""
        # Add a second DAYCARE_ASSIGNMENT to elder_2
        cr_extra = CareRelationship(
            elder_id=seed_data["elder_2_id"],
            actor_id=seed_data["daycare_worker_id"],
            tenant_id=seed_data["tenant_a_id"],
            care_unit_id=seed_data["care_unit_a_id"],
            relationship_type="DAYCARE_ASSIGNMENT",
            scope=["elder:basic:read"],
            status="ACTIVE",
            effective_from=NOW - timedelta(days=10),
            effective_to=None,
        )
        db_session.add(cr_extra)
        await db_session.flush()

        repo = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])
        results = await repo.find_authorized_elders_by_actor(
            actor_id=seed_data["daycare_worker_id"],
            relationship_types=["DAYCARE_ASSIGNMENT"],
            current_time=NOW,
        )
        assert len(results) == 2
        # "Elder One" < "Elder Two" alphabetically
        assert results[0].display_name == "Elder One"
        assert results[1].display_name == "Elder Two"


# ─── CareAssignmentRepository Tests ──────────────────────────────────────────


class TestCareAssignmentFindValidForWorker:
    """Tests for CareAssignmentRepository.find_valid_for_worker."""

    async def test_finds_confirmed_assignment(self, db_session, seed_data):
        """CONFIRMED assignment within time window is found."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        result = await repo.find_valid_for_worker(
            worker_id=seed_data["worker_id"],
            elder_id=seed_data["elder_1_id"],
            current_time=NOW,
        )
        assert result is not None
        assert result.worker_id == seed_data["worker_id"]
        assert result.elder_id == seed_data["elder_1_id"]
        assert result.status == "CONFIRMED"

    async def test_finds_in_progress_assignment(self, db_session, seed_data):
        """IN_PROGRESS assignment within time window is found."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        result = await repo.find_valid_for_worker(
            worker_id=seed_data["worker_id"],
            elder_id=seed_data["elder_2_id"],
            current_time=NOW,
        )
        assert result is not None
        assert result.status == "IN_PROGRESS"

    async def test_returns_none_for_draft_assignment(self, db_session, seed_data):
        """DRAFT assignment returns None (not an active status)."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        result = await repo.find_valid_for_worker(
            worker_id=seed_data["other_worker_id"],
            elder_id=seed_data["elder_1_id"],
            current_time=NOW,
        )
        assert result is None

    async def test_returns_none_for_expired_time_window(self, db_session, seed_data):
        """Assignment outside time window (past service_end) returns None."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        # Query after the active assignment's service_end
        future_time = NOW + timedelta(hours=10)
        result = await repo.find_valid_for_worker(
            worker_id=seed_data["worker_id"],
            elder_id=seed_data["elder_1_id"],
            current_time=future_time,
        )
        assert result is None

    async def test_returns_none_for_wrong_worker(self, db_session, seed_data):
        """Querying with wrong worker_id returns None."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        result = await repo.find_valid_for_worker(
            worker_id=seed_data["other_worker_id"],
            elder_id=seed_data["elder_2_id"],
            current_time=NOW,
        )
        assert result is None

    async def test_strict_less_than_service_end(self, db_session, seed_data):
        """At exactly service_end, the assignment is NOT valid (strict <)."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        # service_end of ca_active is NOW + 6 hours
        at_end = NOW + timedelta(hours=6)
        result = await repo.find_valid_for_worker(
            worker_id=seed_data["worker_id"],
            elder_id=seed_data["elder_1_id"],
            current_time=at_end,
        )
        assert result is None

    async def test_at_service_start_is_valid(self, db_session, seed_data):
        """At exactly service_start, the assignment IS valid (<=)."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        # service_start of ca_active is NOW - 2 hours
        at_start = NOW - timedelta(hours=2)
        result = await repo.find_valid_for_worker(
            worker_id=seed_data["worker_id"],
            elder_id=seed_data["elder_1_id"],
            current_time=at_start,
        )
        assert result is not None


class TestCareAssignmentAuthorizedElders:
    """Tests for CareAssignmentRepository.find_authorized_elders_by_worker."""

    async def test_home_care_mode_returns_elders(self, db_session, seed_data):
        """Home-care mode returns elders with active assignments."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        results = await repo.find_authorized_elders_by_worker(
            worker_id=seed_data["worker_id"],
            current_time=NOW,
        )
        # worker has CONFIRMED -> elder_1 and IN_PROGRESS -> elder_2
        assert len(results) == 2
        elder_ids = {r.elder_id for r in results}
        assert seed_data["elder_1_id"] in elder_ids
        assert seed_data["elder_2_id"] in elder_ids

    async def test_excludes_draft_assignments(self, db_session, seed_data):
        """DRAFT assignments do not appear in results."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        results = await repo.find_authorized_elders_by_worker(
            worker_id=seed_data["other_worker_id"],
            current_time=NOW,
        )
        assert len(results) == 0

    async def test_excludes_expired_assignments(self, db_session, seed_data):
        """Assignments past service_end do not appear."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        # At a time after all assignments have ended
        future_time = NOW + timedelta(hours=24)
        results = await repo.find_authorized_elders_by_worker(
            worker_id=seed_data["worker_id"],
            current_time=future_time,
        )
        assert len(results) == 0

    async def test_results_include_care_unit_name(self, db_session, seed_data):
        """Each result includes the care_unit_name from the joined CareUnit."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        results = await repo.find_authorized_elders_by_worker(
            worker_id=seed_data["worker_id"],
            current_time=NOW,
        )
        for r in results:
            assert r.care_unit_name == "Unit A"

    async def test_results_ordered_by_display_name(self, db_session, seed_data):
        """Results are ordered by display_name, then elder_id."""
        repo = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])
        results = await repo.find_authorized_elders_by_worker(
            worker_id=seed_data["worker_id"],
            current_time=NOW,
        )
        # "Elder One" < "Elder Two" alphabetically
        assert results[0].display_name == "Elder One"
        assert results[1].display_name == "Elder Two"


# ─── Tenant Isolation Tests ──────────────────────────────────────────────────


class TestTenantIsolation:
    """Test that tenant isolation is enforced at the repository query level.

    A repository scoped to Tenant A cannot see data belonging to Tenant B,
    even when the same actor has valid relationships/assignments in Tenant B.
    """

    async def test_relationship_repo_isolates_tenants(self, db_session, seed_data):
        """CareRelationshipRepository scoped to Tenant A cannot find Tenant B data."""
        repo_a = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])

        # family_member has a valid FAMILY_SHARE in tenant B to elder_3
        # but querying via tenant A repo should find nothing for elder_3
        result = await repo_a.find_valid_for_actor(
            actor_id=seed_data["family_member_id"],
            elder_id=seed_data["elder_3_id"],
            relationship_type="FAMILY_SHARE",
            current_time=NOW,
        )
        assert result is None

    async def test_assignment_repo_isolates_tenants(self, db_session, seed_data):
        """CareAssignmentRepository scoped to Tenant A cannot find Tenant B data."""
        repo_a = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])

        # worker has a valid assignment in tenant B to elder_3
        # but querying via tenant A repo should find nothing
        result = await repo_a.find_valid_for_worker(
            worker_id=seed_data["worker_id"],
            elder_id=seed_data["elder_3_id"],
            current_time=NOW,
        )
        assert result is None

    async def test_authorized_elders_relationship_isolates_tenants(self, db_session, seed_data):
        """Authorized-elders via relationship does not include cross-tenant elders."""
        repo_a = CareRelationshipRepository(db_session, seed_data["tenant_a_id"])

        results = await repo_a.find_authorized_elders_by_actor(
            actor_id=seed_data["family_member_id"],
            relationship_types=["FAMILY_SHARE", "LEGAL_REPRESENTATIVE"],
            current_time=NOW,
        )
        # Only elder_1 from tenant A, NOT elder_3 from tenant B
        elder_ids = {r.elder_id for r in results}
        assert seed_data["elder_3_id"] not in elder_ids

    async def test_authorized_elders_assignment_isolates_tenants(self, db_session, seed_data):
        """Authorized-elders via assignment does not include cross-tenant elders."""
        repo_a = CareAssignmentRepository(db_session, seed_data["tenant_a_id"])

        results = await repo_a.find_authorized_elders_by_worker(
            worker_id=seed_data["worker_id"],
            current_time=NOW,
        )
        # Only elder_1, elder_2 from tenant A, NOT elder_3 from tenant B
        elder_ids = {r.elder_id for r in results}
        assert seed_data["elder_3_id"] not in elder_ids

    async def test_tenant_b_sees_own_data(self, db_session, seed_data):
        """Repository scoped to Tenant B correctly sees its own data."""
        repo_b = CareAssignmentRepository(db_session, seed_data["tenant_b_id"])

        result = await repo_b.find_valid_for_worker(
            worker_id=seed_data["worker_id"],
            elder_id=seed_data["elder_3_id"],
            current_time=NOW,
        )
        assert result is not None
        assert result.tenant_id == seed_data["tenant_b_id"]

    async def test_tenant_b_relationship_visible(self, db_session, seed_data):
        """Repository scoped to Tenant B finds relationships in Tenant B."""
        repo_b = CareRelationshipRepository(db_session, seed_data["tenant_b_id"])

        result = await repo_b.find_valid_for_actor(
            actor_id=seed_data["family_member_id"],
            elder_id=seed_data["elder_3_id"],
            relationship_type="FAMILY_SHARE",
            current_time=NOW,
        )
        assert result is not None
        assert result.tenant_id == seed_data["tenant_b_id"]
