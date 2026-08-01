"""Integration tests for Identity and Elder API endpoints.

Tests the full HTTP request/response cycle via AsyncClient with a real
database (PostgreSQL via Docker). Uses FakeAuthenticator to inject known
ActorContext values.

Validates:
- GET /api/v1/me returns correct actor info (Req 10.1)
- GET /api/v1/me/authorized-elders for various modes (Req 10.1, 11.1)
- GET /api/v1/elders/{elder_id} authorized and non-authorized paths (Req 12.1, 12.2, 12.3)
- GET /api/v1/elders/{elder_id}/access-context complete flow (Req 11.1)
- Non-disclosure: not-found vs unauthorized responses are identical (Req 14.1, 14.2)

Requirements: 10.1, 11.1, 12.1, 12.2, 12.3, 14.1, 14.2
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_db_engine
from app.main import create_app
from app.middleware.auth import FakeAuthenticator, get_authenticator
from app.models.actor import Actor
from app.models.care_assignment import CareAssignment
from app.models.care_relationship import CareRelationship
from app.models.care_unit import CareUnit
from app.models.elder import Elder
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant

# ─── Fixed time ──────────────────────────────────────────────────────────────
#
# Unlike test_repositories.py (which calls repository methods directly with an
# explicit `current_time` argument), these tests exercise the real HTTP
# endpoints, which always evaluate authorization against the actual wall-clock
# time (`datetime.now(UTC)` in app/api/elders.py and app/api/identity.py) —
# by design, a client can never inject its own "current time" into an
# authorization decision. So the bounded CareAssignment window below must
# straddle real "now", not a fixed historical date, or it silently expires as
# real time moves on. Open-ended CareRelationships (effective_to=None) aren't
# affected since they have no upper bound to outlive.
NOW = datetime.now(UTC)


# ─── Helper: build client with custom ActorContext ───────────────────────────


def _build_client_app(test_engine, actor_id: uuid.UUID, actor_role: str, tenant_id: uuid.UUID):
    """Build a FastAPI app with dependency overrides for a given actor context."""
    app = create_app()
    fake_auth = FakeAuthenticator(
        actor_id=actor_id,
        actor_role=actor_role,
        tenant_id=tenant_id,
    )
    test_db_engine = _TestDatabaseEngine(test_engine)
    app.dependency_overrides[get_authenticator] = lambda: fake_auth
    app.dependency_overrides[get_db_engine] = lambda: test_db_engine
    return app


class _TestDatabaseEngine:
    """Minimal wrapper around a test engine to satisfy DatabaseEngine interface."""

    def __init__(self, engine):
        self._engine = engine
        self._session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    @property
    def engine(self):
        return self._engine

    @property
    def session_factory(self):
        return self._session_factory

    @property
    def is_ready(self) -> bool:
        return True

    async def check_connectivity(self) -> bool:
        return True


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def api_ids():
    """Fixed UUIDs used across all API integration tests."""
    return {
        "tenant_id": uuid.UUID("10000000-0000-4000-a000-000000000001"),
        "tenant_b_id": uuid.UUID("10000000-0000-4000-a000-000000000002"),
        "worker_id": uuid.UUID("20000000-0000-4000-a000-000000000001"),
        "daycare_worker_id": uuid.UUID("20000000-0000-4000-a000-000000000002"),
        "family_member_id": uuid.UUID("20000000-0000-4000-a000-000000000003"),
        "role_mismatch_id": uuid.UUID("20000000-0000-4000-a000-000000000004"),
        "elder_1_id": uuid.UUID("30000000-0000-4000-a000-000000000001"),
        "elder_2_id": uuid.UUID("30000000-0000-4000-a000-000000000002"),
        "elder_3_id": uuid.UUID("30000000-0000-4000-a000-000000000003"),
        "care_unit_id": uuid.UUID("40000000-0000-4000-a000-000000000001"),
    }


@pytest_asyncio.fixture
async def seed_api_data(committed_session, api_ids):
    """Seed the database with data for API integration tests.

    Uses committed_session so data is visible across connections.
    """
    ids = api_ids

    # None of the models below declare an ORM `relationship()` (see
    # app/models/*.py — they use plain `mapped_column(..., ForeignKey(...))`),
    # so SQLAlchemy's unit-of-work cannot infer flush order from FK columns
    # alone. With real foreign keys now enforced by the baseline schema, rows
    # must be flushed in dependency order explicitly: Tenant/Actor first,
    # then CareUnit/Elder (depend on Tenant), then memberships/relationships/
    # assignments (depend on all of the above).

    # Tenants
    tenant = Tenant(id=ids["tenant_id"], name="Test Tenant", tenant_type="CARE_ORGANIZATION")
    tenant_b = Tenant(id=ids["tenant_b_id"], name="Tenant B", tenant_type="HOME_CARE_PROVIDER")
    committed_session.add_all([tenant, tenant_b])

    # Actors
    worker = Actor(id=ids["worker_id"], actor_type="HOME_CARE_WORKER", display_name="Worker One")
    daycare_worker = Actor(
        id=ids["daycare_worker_id"], actor_type="DAYCARE_CARE_WORKER", display_name="DC Worker"
    )
    family_member = Actor(
        id=ids["family_member_id"], actor_type="FAMILY_MEMBER", display_name="Family One"
    )
    role_mismatch_actor = Actor(
        id=ids["role_mismatch_id"],
        actor_type="DAYCARE_CARE_WORKER",
        display_name="Mismatched Worker",
    )
    committed_session.add_all([worker, daycare_worker, family_member, role_mismatch_actor])
    await committed_session.flush()

    # Care Unit (depends on Tenant)
    care_unit = CareUnit(
        id=ids["care_unit_id"],
        tenant_id=ids["tenant_id"],
        unit_type="DAYCARE_CENTER",
        name="Main Unit",
    )
    committed_session.add(care_unit)
    await committed_session.flush()

    # Elders (depend on Tenant)
    elder_1 = Elder(
        id=ids["elder_1_id"],
        tenant_id=ids["tenant_id"],
        display_name="Elder Alice",
        primary_care_setting="DAYCARE",
    )
    elder_2 = Elder(
        id=ids["elder_2_id"],
        tenant_id=ids["tenant_id"],
        display_name="Elder Bob",
        primary_care_setting="DAYCARE",
    )
    # Elder in tenant B — for cross-tenant tests
    elder_3 = Elder(
        id=ids["elder_3_id"],
        tenant_id=ids["tenant_b_id"],
        display_name="Elder Charlie",
        primary_care_setting="HOME_CARE",
    )
    committed_session.add_all([elder_1, elder_2, elder_3])
    await committed_session.flush()

    # actor_tenant_membership rows (TenantMembership + CareUnitMembership merged
    # into ActorTenantMembership — see app/models/membership.py). A row with
    # care_unit_id set counts as BOTH a tenant membership (TenantMembershipRepository
    # doesn't filter on care_unit_id) AND a care-unit membership, so the daycare
    # worker only needs one row to satisfy both old memberships.
    tm_daycare = ActorTenantMembership(
        actor_id=ids["daycare_worker_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=ids["care_unit_id"],
        role_code="DAYCARE_CARE_WORKER",
    )
    tm_worker = ActorTenantMembership(
        actor_id=ids["worker_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=None,
        role_code="HOME_CARE_WORKER",
    )
    tm_family = ActorTenantMembership(
        actor_id=ids["family_member_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=None,
        role_code="FAMILY_MEMBER",
    )
    tm_role_mismatch = ActorTenantMembership(
        actor_id=ids["role_mismatch_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=None,
        role_code="FAMILY_MEMBER",
    )
    committed_session.add_all([tm_daycare, tm_worker, tm_family, tm_role_mismatch])
    await committed_session.flush()

    # CareRelationships
    # 1) DAYCARE_ASSIGNMENT for daycare_worker -> elder_1
    cr_daycare = CareRelationship(
        elder_id=ids["elder_1_id"],
        actor_id=ids["daycare_worker_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=ids["care_unit_id"],
        relationship_type="DAYCARE_ASSIGNMENT",
        scope=["elder:basic:read", "elder:access_context:read"],
        status="ACTIVE",
        effective_from=NOW - timedelta(days=30),
        effective_to=None,
    )
    # 2) FAMILY_SHARE for family_member -> elder_1
    cr_family = CareRelationship(
        elder_id=ids["elder_1_id"],
        actor_id=ids["family_member_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=None,
        relationship_type="FAMILY_SHARE",
        scope=["elder:basic:read", "elder:access_context:read"],
        status="ACTIVE",
        effective_from=NOW - timedelta(days=60),
        effective_to=None,
    )
    committed_session.add_all([cr_daycare, cr_family])
    await committed_session.flush()

    # CareAssignment for worker -> elder_2
    ca_active = CareAssignment(
        care_unit_id=ids["care_unit_id"],
        elder_id=ids["elder_2_id"],
        worker_id=ids["worker_id"],
        tenant_id=ids["tenant_id"],
        service_start=NOW - timedelta(hours=2),
        service_end=NOW + timedelta(hours=6),
        service_scope=["elder:basic:read", "elder:access_context:read"],
        status="CONFIRMED",
    )
    committed_session.add(ca_active)

    await committed_session.commit()

    yield ids


# ─── Test: GET /api/v1/me ────────────────────────────────────────────────────


class TestGetMe:
    """Tests for GET /api/v1/me endpoint."""

    @pytest.mark.asyncio
    async def test_returns_actor_profile(self, test_engine, seed_api_data):
        """GET /me returns actor profile with care_unit_ids."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["daycare_worker_id"],
            actor_role="DAYCARE_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "meta" in body
        data = body["data"]
        assert data["actor_id"] == str(ids["daycare_worker_id"])
        assert data["actor_type"] == "DAYCARE_CARE_WORKER"
        assert data["display_name"] == "DC Worker"
        assert data["tenant_id"] == str(ids["tenant_id"])
        assert data["role"] == "DAYCARE_CARE_WORKER"
        assert isinstance(data["care_unit_ids"], list)
        assert str(ids["care_unit_id"]) in data["care_unit_ids"]

    @pytest.mark.asyncio
    async def test_rejects_tenant_membership_role_mismatch(self, test_engine, seed_api_data):
        """A global actor type cannot substitute for a different tenant-local role."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["role_mismatch_id"],
            actor_role="DAYCARE_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_worker_returns_empty_care_units(self, test_engine, seed_api_data):
        """GET /me for a worker without care unit memberships returns empty list."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["care_unit_ids"] == []


# ─── Test: GET /api/v1/me/authorized-elders ──────────────────────────────────


class TestGetAuthorizedElders:
    """Tests for GET /api/v1/me/authorized-elders endpoint."""

    @pytest.mark.asyncio
    async def test_family_mode_returns_elders(self, test_engine, seed_api_data):
        """Family mode returns elders the family member is authorized for."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=family")

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert "items" in data
        assert "page" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["elder_id"] == str(ids["elder_1_id"])
        assert data["items"][0]["display_name"] == "Elder Alice"

    @pytest.mark.asyncio
    async def test_home_care_mode_returns_elders(self, test_engine, seed_api_data):
        """Home-care mode returns elders the worker has active assignments for."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["worker_id"],
            actor_role="HOME_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=home-care")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["elder_id"] == str(ids["elder_2_id"])

    @pytest.mark.asyncio
    async def test_daycare_mode_returns_elders(self, test_engine, seed_api_data):
        """Daycare mode returns elders the daycare worker is authorized for."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["daycare_worker_id"],
            actor_role="DAYCARE_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=daycare")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["elder_id"] == str(ids["elder_1_id"])
        assert data["items"][0]["display_name"] == "Elder Alice"

    @pytest.mark.asyncio
    async def test_invalid_mode_returns_422(self, test_engine, seed_api_data):
        """Invalid mode value returns 422 validation error."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["worker_id"],
            actor_role="HOME_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=invalid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_incompatible_role_mode_returns_403(self, test_engine, seed_api_data):
        """Incompatible role/mode pair returns 403."""
        ids = seed_api_data
        # FAMILY_MEMBER trying daycare mode → 403
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=daycare")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_pagination_metadata_present(self, test_engine, seed_api_data):
        """Response includes pagination metadata."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=family&limit=10")

        assert response.status_code == 200
        page = response.json()["data"]["page"]
        assert "has_more" in page
        assert "limit" in page
        assert page["has_more"] is False
        assert page["limit"] == 10


# ─── Test: GET /api/v1/elders/{elder_id} ─────────────────────────────────────


class TestGetElder:
    """Tests for GET /api/v1/elders/{elder_id} endpoint."""

    @pytest.mark.asyncio
    async def test_authorized_access_returns_200(self, test_engine, seed_api_data):
        """Authorized actor gets 200 with elder data."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_1_id']}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["elder_id"] == str(ids["elder_1_id"])
        assert data["display_name"] == "Elder Alice"
        assert data["status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_unauthorized_access_returns_404(self, test_engine, seed_api_data):
        """Unauthorized actor gets 404 (non-disclosure)."""
        ids = seed_api_data
        # family_member has no relationship to elder_2
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_2_id']}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_elder_returns_404(self, test_engine, seed_api_data):
        """Non-existent elder_id returns 404."""
        ids = seed_api_data
        non_existent_id = uuid.UUID("99999999-9999-4999-9999-999999999999")
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{non_existent_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_non_disclosure_responses_identical(self, test_engine, seed_api_data):
        """Unauthorized and non-existent elder responses are structurally identical.

        This validates the non-disclosure pattern: an attacker cannot
        distinguish between 'elder exists but I'm not authorized' and
        'elder does not exist'.
        """
        ids = seed_api_data
        non_existent_id = uuid.UUID("99999999-9999-4999-9999-999999999999")

        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Unauthorized: elder_2 exists but actor lacks access
            resp_unauthorized = await client.get(f"/api/v1/elders/{ids['elder_2_id']}")
            # Non-existent: random UUID
            resp_nonexistent = await client.get(f"/api/v1/elders/{non_existent_id}")

        # Same status code
        assert resp_unauthorized.status_code == 404
        assert resp_nonexistent.status_code == 404

        # Same response body structure and error code
        body_unauth = resp_unauthorized.json()
        body_nonexist = resp_nonexistent.json()

        assert "error" in body_unauth
        assert "error" in body_nonexist
        assert body_unauth["error"]["code"] == body_nonexist["error"]["code"]
        assert body_unauth["error"]["message"] == body_nonexist["error"]["message"]

    @pytest.mark.asyncio
    async def test_home_care_worker_authorized(self, test_engine, seed_api_data):
        """HOME_CARE_WORKER with valid assignment gets 200."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["worker_id"],
            actor_role="HOME_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_2_id']}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["elder_id"] == str(ids["elder_2_id"])
        assert data["display_name"] == "Elder Bob"


# ─── Test: GET /api/v1/elders/{elder_id}/access-context ──────────────────────


class TestGetElderAccessContext:
    """Tests for GET /api/v1/elders/{elder_id}/access-context endpoint."""

    @pytest.mark.asyncio
    async def test_authorized_returns_access_context(self, test_engine, seed_api_data):
        """Authorized actor gets 200 with access context details."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_1_id']}/access-context")

        assert response.status_code == 200
        data = response.json()["data"]
        assert "purpose" in data
        assert "allowed_actions" in data
        assert "source_type" in data
        assert isinstance(data["allowed_actions"], list)
        assert len(data["allowed_actions"]) > 0

    @pytest.mark.asyncio
    async def test_unauthorized_returns_404(self, test_engine, seed_api_data):
        """Unauthorized actor gets 404 for access-context (non-disclosure)."""
        ids = seed_api_data
        # family_member has no relationship to elder_2
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_2_id']}/access-context")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_elder_returns_404(self, test_engine, seed_api_data):
        """Non-existent elder returns 404 for access-context."""
        ids = seed_api_data
        non_existent_id = uuid.UUID("99999999-9999-4999-9999-999999999999")
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{non_existent_id}/access-context")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_non_disclosure_access_context(self, test_engine, seed_api_data):
        """Access-context: unauthorized vs non-existent responses are identical."""
        ids = seed_api_data
        non_existent_id = uuid.UUID("99999999-9999-4999-9999-999999999999")

        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_unauthorized = await client.get(
                f"/api/v1/elders/{ids['elder_2_id']}/access-context"
            )
            resp_nonexistent = await client.get(f"/api/v1/elders/{non_existent_id}/access-context")

        assert resp_unauthorized.status_code == 404
        assert resp_nonexistent.status_code == 404

        body_unauth = resp_unauthorized.json()
        body_nonexist = resp_nonexistent.json()

        assert body_unauth["error"]["code"] == body_nonexist["error"]["code"]
        assert body_unauth["error"]["message"] == body_nonexist["error"]["message"]

    @pytest.mark.asyncio
    async def test_home_care_worker_access_context(self, test_engine, seed_api_data):
        """HOME_CARE_WORKER with valid assignment gets access-context."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["worker_id"],
            actor_role="HOME_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_2_id']}/access-context")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["purpose"] == "elder_care_access"
        assert "elder:basic:read" in data["allowed_actions"]
