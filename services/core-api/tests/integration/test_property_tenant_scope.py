"""Property-based test: Tenant-scope non-expansion.

**Validates: Requirements 4.7, 12.2**

Property 2: For any query via BaseRepository(tenant_id=X), results never
contain tenant_id != X. This proves that tenant isolation is enforced at
the data layer — cross-tenant leakage is impossible.

Uses Hypothesis with min 100 examples and a real PostgreSQL database.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis.strategies import integers, lists, uuids
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db.base import Base, BaseModel, TenantScopedMixin
from app.repositories.base import BaseRepository

# ─── Test-only model ─────────────────────────────────────────────────────────


class TenantScopedTestEntity(BaseModel, TenantScopedMixin):
    """Test-only entity for property testing tenant scope isolation."""

    __tablename__ = "test_tenant_scope_prop"
    __pk_name__ = "test_tenant_scope_prop_id"


# ─── Module-level engine setup ───────────────────────────────────────────────

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun_test",
)

# NullPool: `_run_async` opens a fresh event loop per Hypothesis example (see
# below). A pooled asyncpg connection created under one example's loop is
# invalid once that loop is closed; reusing it from the next example's new
# loop raises `InterfaceError: cannot perform operation: another operation is
# in progress` / `RuntimeError: Event loop is closed`. NullPool opens (and
# fully closes) a genuine fresh connection every checkout/checkin, so no
# connection ever outlives the loop it was created on.
_engine = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def _run_async(coro):
    """Run an async coroutine synchronously for use inside Hypothesis tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def create_test_table():
    """Create the test table before running property tests, drop after."""

    async def _setup():
        async with _engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[TenantScopedTestEntity.__table__],
            )

    async def _teardown():
        async with _engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.drop_all,
                tables=[TenantScopedTestEntity.__table__],
            )
        await _engine.dispose()

    _run_async(_setup())
    yield
    _run_async(_teardown())


# ─── Property Test ───────────────────────────────────────────────────────────


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    target_tenant=uuids(version=4),
    other_tenants=lists(uuids(version=4), min_size=1, max_size=5),
    entities_per_tenant=integers(min_value=1, max_value=3),
)
def test_tenant_scope_non_expansion(
    target_tenant: uuid.UUID,
    other_tenants: list[uuid.UUID],
    entities_per_tenant: int,
    create_test_table,  # noqa: ARG001 — ensures table exists
) -> None:
    """Property: BaseRepository(tenant_id=X).list_all() never returns rows with tenant_id != X.

    **Validates: Requirements 4.7, 12.2**

    Strategy:
    1. Generate a target tenant UUID and 1-5 other tenant UUIDs
    2. Insert entities for target_tenant AND other tenants
    3. Query via BaseRepository(tenant_id=target_tenant)
    4. Assert every returned row has tenant_id == target_tenant
    """

    async def _run():
        async with _engine.begin() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                # Ensure target_tenant is distinct from other_tenants
                all_tenants = [target_tenant] + [t for t in other_tenants if t != target_tenant]

                # Insert entities for all tenants
                for tenant_id in all_tenants:
                    for _ in range(entities_per_tenant):
                        entity = TenantScopedTestEntity(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                        )
                        session.add(entity)
                await session.flush()

                # Query via BaseRepository scoped to target_tenant
                repo = BaseRepository(session, target_tenant)
                results = await repo.list_all(TenantScopedTestEntity, limit=1000)

                # PROPERTY: Every result must belong to the target tenant
                for entity in results:
                    assert entity.tenant_id == target_tenant, (
                        f"Tenant scope violated: expected tenant_id={target_tenant}, "
                        f"got tenant_id={entity.tenant_id}"
                    )

                # Also verify get_by_id never returns a cross-tenant entity
                # by attempting to fetch an entity belonging to another tenant
                if len(all_tenants) > 1:
                    # Insert a known entity for a different tenant
                    other_tenant = all_tenants[1]
                    other_entity = TenantScopedTestEntity(
                        id=uuid.uuid4(),
                        tenant_id=other_tenant,
                    )
                    session.add(other_entity)
                    await session.flush()

                    # Trying to fetch it via the target tenant's repo must return None
                    result = await repo.get_by_id(TenantScopedTestEntity, other_entity.id)
                    assert result is None, (
                        f"get_by_id returned cross-tenant entity: "
                        f"requested tenant={target_tenant}, "
                        f"entity tenant={other_entity.tenant_id}"
                    )
            finally:
                await session.close()
                # Rollback the transaction to keep DB clean between examples
                await conn.rollback()

    _run_async(_run())
