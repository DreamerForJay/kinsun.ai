"""Property-based test: Outbox atomicity.

**Validates: Requirements 13.3, 13.4**

Property 5: Committed transaction — both entity and outbox entry visible;
rolled-back transaction — neither persisted. This proves that the outbox
write is atomic with the originating entity change.

Uses Hypothesis with min 100 examples and a real PostgreSQL database.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis.strategies import characters, dictionaries, text, uuids
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db.base import Base, BaseModel, TenantScopedMixin
from app.events.outbox_writer import RESTRICTED_PAYLOAD_KEYS, write_outbox_entry
from app.models.outbox import OutboxEvent
from app.models.tenant import Tenant

# ─── Test-only model ─────────────────────────────────────────────────────────


class OutboxAtomTestEntity(BaseModel, TenantScopedMixin):
    """Test-only entity for property testing outbox atomicity."""

    __tablename__ = "test_outbox_atom_prop"
    __pk_name__ = "test_outbox_atom_prop_id"


# ─── Module-level engine setup ───────────────────────────────────────────────

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://kinsun:kinsun_dev@localhost:5432/kinsun_test",
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
def create_test_tables():
    """Create the test entity table and outbox table before tests, drop after."""

    async def _setup():
        async with _engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[
                    OutboxAtomTestEntity.__table__,
                    OutboxEvent.__table__,
                ],
            )

    async def _teardown():
        async with _engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.drop_all,
                tables=[OutboxAtomTestEntity.__table__],
            )
        await _engine.dispose()

    _run_async(_setup())
    yield
    _run_async(_teardown())


# ─── Hypothesis strategies ───────────────────────────────────────────────────

_event_types = text(
    alphabet="abcdefghijklmnopqrstuvwxyz._",
    min_size=1,
    max_size=50,
)

_payload_keys = text(
    alphabet="abcdefghijklmnopqrstuvwxyz_",
    min_size=1,
    max_size=10,
).filter(lambda key: key.lower() not in RESTRICTED_PAYLOAD_KEYS)

_payloads = dictionaries(
    # Atomicity is defined for valid events. Restricted payload rejection is
    # covered separately and must not turn this property into a validation test.
    keys=_payload_keys,
    # Excludes the NUL character: PostgreSQL's text/JSONB types cannot store
    # it (raises "unsupported Unicode escape sequence") — a real Postgres
    # limitation, not something write_outbox_entry should (or could) work
    # around.
    values=text(
        alphabet=characters(
            exclude_categories=("Cs",),
            exclude_characters="\x00",
        ),
        min_size=0,
        max_size=20,
    ),
    min_size=0,
    max_size=5,
)


# ─── Property Test ───────────────────────────────────────────────────────────


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    entity_id=uuids(version=4),
    tenant_id=uuids(version=4),
    event_id=uuids(version=4),
    event_type=_event_types,
    payload=_payloads,
)
def test_outbox_atomicity(
    entity_id: uuid.UUID,
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    event_type: str,
    payload: dict,
    create_test_tables,  # noqa: ARG001 — ensures tables exist
) -> None:
    """Property: Committed txn persists both entity and outbox; rollback persists neither.

    **Validates: Requirements 13.3, 13.4**

    Strategy:
    1. Generate random entity UUID, tenant UUID, event_id, event_type, payload
    2. COMMITTED PATH: insert a real Tenant (outbox_event.tenant_id is now a real
       FOREIGN KEY to tenant.tenant_id — see app/models/outbox.py) + entity +
       write_outbox_entry, commit, verify both visible
    3. ROLLED-BACK PATH: insert entity + write_outbox_entry (reusing the same,
       already-committed Tenant), rollback, verify neither the entity nor the
       outbox event is persisted
    4. Clean up committed data for test isolation

    aggregate_type and trace_id are fixed, non-empty strings here (required
    NOT NULL columns — see app/events/outbox_writer.py); this test is about
    write atomicity, not about validating those specific values.
    """

    async def _run():
        # Use a unique event_id for the rollback path to avoid conflict
        rollback_event_id = uuid.uuid4()
        rollback_entity_id = uuid.uuid4()

        # ── COMMITTED PATH ──────────────────────────────────────────────
        async with _engine.begin() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                # Insert the tenant referenced by the outbox event's FK, plus the entity
                tenant = Tenant(
                    id=tenant_id,
                    tenant_type="DEMO",
                    name="Outbox Atomicity Property Test Tenant",
                )
                entity = OutboxAtomTestEntity(
                    id=entity_id,
                    tenant_id=tenant_id,
                )
                session.add_all([tenant, entity])
                await session.flush()

                # Write outbox entry in the same transaction
                await write_outbox_entry(
                    session=session,
                    event_type=event_type,
                    aggregate_type="OutboxAtomTestEntity",
                    aggregate_id=entity_id,
                    tenant_id=tenant_id,
                    payload=payload,
                    trace_id=str(uuid.uuid4()),
                    event_id=event_id,
                )
            finally:
                await session.close()
            # Transaction commits when exiting `begin()` context without exception

        # Verify BOTH are visible from a separate connection
        async with _engine.connect() as verify_conn:
            verify_session = AsyncSession(bind=verify_conn, expire_on_commit=False)
            try:
                # Entity must be visible
                entity_result = await verify_session.execute(
                    select(OutboxAtomTestEntity).where(OutboxAtomTestEntity.id == entity_id)
                )
                found_entity = entity_result.scalar_one_or_none()
                assert found_entity is not None, f"Committed entity not visible: id={entity_id}"
                assert found_entity.tenant_id == tenant_id

                # Outbox entry must be visible (looked up by the event_id UNIQUE
                # column, not the PK — outbox_event_id is a separate, independently
                # generated primary key)
                outbox_result = await verify_session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_id == event_id)
                )
                found_outbox = outbox_result.scalar_one_or_none()
                assert (
                    found_outbox is not None
                ), f"Committed outbox entry not visible: event_id={event_id}"
                assert found_outbox.aggregate_id == entity_id
                assert found_outbox.tenant_id == tenant_id
                assert found_outbox.event_type == event_type
            finally:
                await verify_session.close()

        # ── ROLLED-BACK PATH ────────────────────────────────────────────
        conn = await _engine.connect()
        transaction = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            # Insert entity (the tenant already exists, committed above)
            rollback_entity = OutboxAtomTestEntity(
                id=rollback_entity_id,
                tenant_id=tenant_id,
            )
            session.add(rollback_entity)
            await session.flush()

            # Write outbox entry in the same transaction
            await write_outbox_entry(
                session=session,
                event_type=event_type,
                aggregate_type="OutboxAtomTestEntity",
                aggregate_id=rollback_entity_id,
                tenant_id=tenant_id,
                payload=payload,
                trace_id=str(uuid.uuid4()),
                event_id=rollback_event_id,
            )

            # Explicitly ROLLBACK
            await transaction.rollback()
        finally:
            await session.close()
            await conn.close()

        # Verify NEITHER is visible from a separate connection
        async with _engine.connect() as verify_conn:
            verify_session = AsyncSession(bind=verify_conn, expire_on_commit=False)
            try:
                # Entity must NOT be visible
                entity_result = await verify_session.execute(
                    select(OutboxAtomTestEntity).where(
                        OutboxAtomTestEntity.id == rollback_entity_id
                    )
                )
                found_entity = entity_result.scalar_one_or_none()
                assert (
                    found_entity is None
                ), f"Rolled-back entity should not be visible: id={rollback_entity_id}"

                # Outbox entry must NOT be visible
                outbox_result = await verify_session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_id == rollback_event_id)
                )
                found_outbox = outbox_result.scalar_one_or_none()
                assert found_outbox is None, (
                    f"Rolled-back outbox entry should not be visible: "
                    f"event_id={rollback_event_id}"
                )
            finally:
                await verify_session.close()

        # ── CLEANUP committed data ──────────────────────────────────────
        # Delete children (entity, outbox event) before the tenant they
        # reference — outbox_event.tenant_id is a real FK.
        async with _engine.begin() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                entity_to_delete = await session.get(OutboxAtomTestEntity, entity_id)
                if entity_to_delete:
                    await session.delete(entity_to_delete)

                outbox_result = await session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_id == event_id)
                )
                outbox_to_delete = outbox_result.scalar_one_or_none()
                if outbox_to_delete:
                    await session.delete(outbox_to_delete)
                await session.flush()
            finally:
                await session.close()

        async with _engine.begin() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                tenant_to_delete = await session.get(Tenant, tenant_id)
                if tenant_to_delete:
                    await session.delete(tenant_to_delete)
                await session.flush()
            finally:
                await session.close()

    _run_async(_run())
