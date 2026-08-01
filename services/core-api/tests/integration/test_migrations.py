"""Migration verification tests.

Validates that Alembic migrations can be applied and rolled back cleanly,
ensuring schema changes do not break deployment pipelines.

These tests manage their own database state independently from the
session-scoped migration fixture in conftest.py. Each test starts from
an empty database (the eldercare_ai schema and alembic_version dropped)
and runs upgrade/downgrade sequences manually.

The schema starts from a frozen Alembic baseline (revision f393b4452ce8,
see alembic/versions/20260730_1502_baseline_eldercare_ai_schema_v0_1.py)
that creates the whole `eldercare_ai` schema — 48 tables — in one shot from
a checksummed SQL snapshot. New changes are separate revisions layered on
top; the frozen SQL and expected checksum remain unchanged. Full downgrade
tests intentionally target `base`, then rebuild through every revision.

Validates: Requirements 17.1, 17.2, 17.3, 17.4
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from alembic import command
from alembic.config import Config

# ─── Helpers ─────────────────────────────────────────────────────────────────
#
# `test_engine` here is conftest.py's session-scoped fixture — it uses
# NullPool (see conftest.py), so every checkout is a genuinely fresh
# connection. That matters here specifically: this module runs many
# DROP SCHEMA / CREATE SCHEMA cycles, and a pooled connection reused across
# that much schema churn hits asyncpg connection/prepared-statement-cache
# errors (cached statements or OIDs referring to objects the DDL just
# replaced).

SCHEMA_NAME = "eldercare_ai"

#: The eight tables that back the identity & elder assignment domain.
#: The baseline creates 48 tables in total (the wider eldercare_ai product
#: schema); these are the ones this module's ORM layer and repositories map
#: onto (see app/models/*.py and the table mapping in AGENTS.md).
_CORE_TABLES = sorted(
    [
        "actor",
        "tenant",
        "care_unit",
        "actor_tenant_membership",
        "elder",
        "care_relationship",
        "care_assignment",
        "outbox_event",
    ]
)

#: Total number of tables after upgrading through the current head revision.
_TOTAL_HEAD_TABLE_COUNT = 50

#: The baseline's revision id (see the migration file's Revision ID header).
_BASELINE_REVISION = "f393b4452ce8"
_HEAD_REVISION = "c1a9e7f24b63"


def _get_alembic_config() -> Config:
    """Build an Alembic config pointing to the project's alembic.ini."""
    project_root = os.path.join(os.path.dirname(__file__), "..", "..")
    alembic_cfg = Config(os.path.join(project_root, "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        os.path.join(project_root, "alembic"),
    )
    return alembic_cfg


def _sync_test_database_url() -> str:
    """Async (asyncpg) TEST_DATABASE_URL converted to the sync (psycopg) URL Alembic uses."""
    async_url = os.environ.get("TEST_DATABASE_URL", "")
    return async_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


def _run_alembic_command(command_fn, target: str) -> None:
    """Invoke an Alembic command (upgrade/downgrade) against the TEST database.

    alembic/env.py's run_migrations_online() always builds its own engine from
    the DATABASE_URL environment variable (see alembic/env.py) — it does not
    honor `config.attributes["connection"]`, unlike the more common Alembic
    recipe of injecting a live connection. Since alembic/ must not be edited
    (it is outside tests/), the only way from here to target the test
    database — rather than whatever DATABASE_URL happens to point at (the dev
    database, per this project's documented test-running instructions) — is
    to temporarily point DATABASE_URL at TEST_DATABASE_URL for the duration
    of the call, exactly like conftest.py's session-scoped `run_migrations`
    fixture already does.

    The `connection` argument accepted by callers (via `conn.run_sync(...)`)
    is intentionally unused for the Alembic call itself: env.py ignores it
    and opens its own psycopg connection instead. Plain DDL helpers in this
    module (_drop_all_tables, the introspection helpers) use the passed
    connection directly and are unaffected by this.
    """
    cfg = _get_alembic_config()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _sync_test_database_url()
    try:
        command_fn(cfg, target)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _run_upgrade(connection, target: str = "head") -> None:  # noqa: ARG001 — see _run_alembic_command
    """Run Alembic upgrade to target against the test database."""
    _run_alembic_command(command.upgrade, target)


def _run_downgrade(connection, target: str = "-1") -> None:  # noqa: ARG001 — see _run_alembic_command
    """Run Alembic downgrade to target against the test database."""
    _run_alembic_command(command.downgrade, target)


def _drop_all_tables(connection) -> None:
    """Drop the eldercare_ai schema and alembic_version to start fresh.

    The baseline's downgrade() does exactly this (DROP SCHEMA ... CASCADE),
    but alembic_version lives in `public` (see the migration's downgrade()
    docstring) and is only removed here, not by the migration itself.
    """
    connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE"))
    connection.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))


def _get_alembic_version(connection) -> str | None:
    """Read the current alembic_version from the database."""
    result = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
    row = result.first()
    return row[0] if row else None


def _get_tables(connection) -> list[str]:
    """Get all eldercare_ai tables from information_schema."""
    result = connection.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema ORDER BY table_name"
        ),
        {"schema": SCHEMA_NAME},
    )
    return [row[0] for row in result]


def _get_indexes(connection, table_name: str) -> list[str]:
    """Get index names for a table (excluding primary key indexes)."""
    result = connection.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename = :table_name "
            "AND indexname NOT LIKE '%_pkey'"
        ),
        {"schema": SCHEMA_NAME, "table_name": table_name},
    )
    return [row[0] for row in result]


def _get_check_constraints(connection, table_name: str) -> list[str]:
    """Get user-defined CHECK constraint names for a table in eldercare_ai."""
    result = connection.execute(
        text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "JOIN pg_class rel ON rel.oid = c.conrelid "
            "WHERE n.nspname = :schema AND rel.relname = :table_name AND c.contype = 'c' "
            "ORDER BY c.conname"
        ),
        {"schema": SCHEMA_NAME, "table_name": table_name},
    )
    return [row[0] for row in result]


def _get_unique_constraints(connection, table_name: str) -> list[str]:
    """Get UNIQUE table-constraint names for a table in eldercare_ai.

    Note this only returns constraints created via `UNIQUE (...)`, not
    stand-alone `CREATE UNIQUE INDEX` (e.g. uq_actor_email, uq_membership_scope
    are unique indexes, not table constraints, and show up in _get_indexes
    instead).
    """
    result = connection.execute(
        text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "JOIN pg_class rel ON rel.oid = c.conrelid "
            "WHERE n.nspname = :schema AND rel.relname = :table_name AND c.contype = 'u' "
            "ORDER BY c.conname"
        ),
        {"schema": SCHEMA_NAME, "table_name": table_name},
    )
    return [row[0] for row in result]


def _get_foreign_keys(connection, table_name: str) -> list[str]:
    """Get foreign key constraint names for a table in eldercare_ai."""
    result = connection.execute(
        text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "JOIN pg_class rel ON rel.oid = c.conrelid "
            "WHERE n.nspname = :schema AND rel.relname = :table_name AND c.contype = 'f' "
            "ORDER BY c.conname"
        ),
        {"schema": SCHEMA_NAME, "table_name": table_name},
    )
    return [row[0] for row in result]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _restore_schema_after_module(test_engine):
    """Guarantee the schema is back at head once this module's tests finish.

    Tests in this module intentionally drop and rebuild the eldercare_ai
    schema to exercise Alembic upgrade/downgrade paths. `test_engine` is
    session-scoped and shared with every other integration test module, so
    ending this module with the schema absent (e.g. after
    test_baseline_full_downgrade_to_base) would break every test that runs
    afterwards in the same session. This re-applies `alembic upgrade head`
    once, after the last test in this module, regardless of which one ran
    last.
    """
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")


# ─── Tests: Upgrade / Downgrade Lifecycle ────────────────────────────────────


@pytest.mark.asyncio
async def test_upgrade_from_empty_to_head(test_engine):
    """Verify Alembic upgrade from an empty database to head succeeds.

    Validates: Requirement 17.1
    """
    async with test_engine.begin() as conn:
        # Start with a clean slate
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        # Run upgrade from empty to head
        await conn.run_sync(_run_upgrade, "head")

    # Verify alembic_version is set to the baseline revision
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert (
            version == _HEAD_REVISION
        ), f"Expected head revision '{_HEAD_REVISION}', got '{version}'"

    # Verify the outbox_event table exists
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = 'outbox_event'"
            ),
            {"schema": SCHEMA_NAME},
        )
        tables = [row[0] for row in result]
        assert "outbox_event" in tables, "outbox_event table should exist after upgrade"

        tombstone_result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = 'deletion_tombstone'"
            ),
            {"schema": SCHEMA_NAME},
        )
        assert tombstone_result.scalar_one_or_none() == "deletion_tombstone"


@pytest.mark.asyncio
async def test_dead_letter_status_migration_roundtrip(test_engine):
    """Verify terminal status values and downgrade conversion at the data level."""
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        event_id = await conn.scalar(
            text(
                "INSERT INTO eldercare_ai.outbox_event "
                "(event_id, event_type, aggregate_type, aggregate_id, "
                "aggregate_version, trace_id, payload, delivery_status, "
                "attempt_count, last_error) "
                "VALUES (gen_random_uuid(), 'migration.smoke.v1', 'memory', "
                "gen_random_uuid(), 1, 'trace-migration', '{}'::jsonb, "
                "'DEAD_LETTER', 3, 'PUBLISHER_ATTEMPT_LIMIT_REACHED') "
                "RETURNING event_id"
            )
        )

    with pytest.raises(IntegrityError):
        async with test_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE eldercare_ai.outbox_event "
                    "SET delivery_status = 'UNSUPPORTED' WHERE event_id = :event_id"
                ),
                {"event_id": event_id},
            )

    async with test_engine.begin() as conn:
        # Newer migrations now sit above the dead-letter migration. Target its
        # direct parent so this test still exercises the e4 downgrade itself.
        await conn.run_sync(_run_downgrade, "d3b7e2a4f901")

    async with test_engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT delivery_status, last_error "
                    "FROM eldercare_ai.outbox_event WHERE event_id = :event_id"
                ),
                {"event_id": event_id},
            )
        ).one()
        assert row.delivery_status == "FAILED"
        assert row.last_error == "PUBLISHER_ATTEMPT_LIMIT_REACHED"

    with pytest.raises(IntegrityError):
        async with test_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE eldercare_ai.outbox_event "
                    "SET delivery_status = 'DEAD_LETTER' WHERE event_id = :event_id"
                ),
                {"event_id": event_id},
            )

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")


@pytest.mark.asyncio
async def test_downgrade_from_head_removes_schema(test_engine):
    """Verify Alembic downgrade from head to base removes the schema.

    Validates: Requirement 17.2
    """
    # Start fresh and upgrade to head
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Downgrade through every revision to the empty base.
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_downgrade, "base")

    # Verify alembic_version is now empty (no revisions applied)
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert version is None, f"Expected no version after downgrade, got '{version}'"

    # Verify the eldercare_ai schema itself is gone
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
            {"schema": SCHEMA_NAME},
        )
        assert result.first() is None, "eldercare_ai schema should not exist after downgrade"


@pytest.mark.asyncio
async def test_upgrade_downgrade_upgrade_roundtrip(test_engine):
    """Verify upgrade -> downgrade -> upgrade produces same state as single upgrade.

    Validates: Requirement 17.3
    """
    # Start fresh and do a single upgrade to head to get reference state
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Capture the reference alembic_version after single upgrade
    async with test_engine.begin() as conn:
        reference_version = await conn.run_sync(_get_alembic_version)

    # Now drop everything and do the round-trip: upgrade -> downgrade -> upgrade
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_downgrade, "-1")

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Verify the alembic_version matches the reference
    async with test_engine.begin() as conn:
        roundtrip_version = await conn.run_sync(_get_alembic_version)

    assert roundtrip_version == reference_version, (
        f"Round-trip version '{roundtrip_version}' does not match "
        f"reference version '{reference_version}'"
    )

    # Verify the outbox_event table exists (schema is consistent)
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = 'outbox_event'"
            ),
            {"schema": SCHEMA_NAME},
        )
        tables = [row[0] for row in result]
        assert (
            "outbox_event" in tables
        ), "outbox_event table should exist after round-trip migration"


# ─── Tests: Baseline Schema Objects (identity & elder assignment tables) ─────


@pytest.mark.asyncio
async def test_head_upgrade_creates_expected_tables(test_engine):
    """Verify all migrations through head create 50 tables, including the core 8.

    Validates: Requirement 16.1, 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        tables = await conn.run_sync(_get_tables)

    assert len(tables) == _TOTAL_HEAD_TABLE_COUNT, (
        f"Expected {_TOTAL_HEAD_TABLE_COUNT} tables in eldercare_ai, "
        f"got {len(tables)}: {tables}"
    )
    missing = set(_CORE_TABLES) - set(tables)
    assert not missing, f"Expected core tables {_CORE_TABLES} to be a subset, missing: {missing}"


@pytest.mark.asyncio
async def test_baseline_upgrade_creates_all_indexes(test_engine):
    """Verify the baseline migration creates all expected composite indexes
    on the identity & elder assignment tables.

    Validates: Requirement 16.2, 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    expected_indexes = [
        "idx_actor_status",
        "uq_actor_email",
        "idx_membership_actor_active",
        "uq_membership_scope",
        "idx_elder_tenant_unit",
        "idx_relationship_elder_actor",
        "idx_assignment_worker_time",
        "idx_assignment_elder_time",
        "idx_outbox_pending",
        "uq_care_unit_name",
        "outbox_event_event_id_key",
    ]

    async with test_engine.begin() as conn:
        all_indexes: list[str] = []
        for table in _CORE_TABLES:
            indexes = await conn.run_sync(_get_indexes, table)
            all_indexes.extend(indexes)

    for idx in expected_indexes:
        assert idx in all_indexes, f"Expected index '{idx}' not found. Found: {all_indexes}"


@pytest.mark.asyncio
async def test_baseline_upgrade_creates_check_constraints(test_engine):
    """Verify the baseline migration creates all expected CHECK constraints
    on the identity & elder assignment tables.

    Validates: Requirement 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    expected_checks = [
        "actor_status_check",
        "actor_tenant_membership_status_check",
        "ck_membership_period",
        "care_unit_status_check",
        "elder_primary_care_setting_check",
        "elder_response_length_preference_check",
        "elder_status_check",
        "care_relationship_status_check",
        "ck_care_relationship_period",
        "care_assignment_status_check",
        "care_assignment_version_check",
        "ck_assignment_period",
        "tenant_status_check",
        "outbox_event_aggregate_version_check",
        "outbox_event_attempt_count_check",
        "outbox_event_delivery_status_check",
    ]

    async with test_engine.begin() as conn:
        all_checks: list[str] = []
        for table in _CORE_TABLES:
            checks = await conn.run_sync(_get_check_constraints, table)
            all_checks.extend(checks)

    for chk in expected_checks:
        assert (
            chk in all_checks
        ), f"Expected CHECK constraint '{chk}' not found. Found: {all_checks}"


@pytest.mark.asyncio
async def test_baseline_upgrade_creates_unique_constraints(test_engine):
    """Verify the baseline migration creates all expected UNIQUE constraints
    on the identity & elder assignment tables.

    Note: uq_actor_email and uq_membership_scope are stand-alone unique
    indexes (see test_baseline_upgrade_creates_all_indexes), not table
    constraints, so they are intentionally not asserted here.

    Validates: Requirement 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    expected_unique = [
        "uq_actor_cognito_sub",
        "uq_care_unit_name",
        "outbox_event_event_id_key",
    ]

    async with test_engine.begin() as conn:
        all_unique: list[str] = []
        for table in _CORE_TABLES:
            unique_constraints = await conn.run_sync(_get_unique_constraints, table)
            all_unique.extend(unique_constraints)

    for uq in expected_unique:
        assert uq in all_unique, f"Expected UNIQUE constraint '{uq}' not found. Found: {all_unique}"


@pytest.mark.asyncio
async def test_baseline_upgrade_creates_foreign_keys(test_engine):
    """Verify the baseline migration creates all expected foreign key
    constraints on the identity & elder assignment tables.

    Validates: Requirement 16.3, 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    expected_fks = [
        "care_unit_tenant_id_fkey",
        "actor_tenant_membership_actor_id_fkey",
        "actor_tenant_membership_care_unit_id_fkey",
        "actor_tenant_membership_tenant_id_fkey",
        "elder_tenant_id_fkey",
        "elder_primary_care_unit_id_fkey",
        "care_relationship_elder_id_fkey",
        "care_relationship_actor_id_fkey",
        "care_relationship_tenant_id_fkey",
        "care_relationship_care_unit_id_fkey",
        "care_assignment_tenant_id_fkey",
        "care_assignment_care_unit_id_fkey",
        "care_assignment_elder_id_fkey",
        "care_assignment_worker_actor_id_fkey",
        "outbox_event_tenant_id_fkey",
        "outbox_event_elder_id_fkey",
        "outbox_event_actor_id_fkey",
    ]

    async with test_engine.begin() as conn:
        all_fks: list[str] = []
        for table in _CORE_TABLES:
            fks = await conn.run_sync(_get_foreign_keys, table)
            all_fks.extend(fks)

    for fk in expected_fks:
        assert fk in all_fks, f"Expected FK constraint '{fk}' not found. Found: {all_fks}"


@pytest.mark.asyncio
async def test_baseline_roundtrip_upgrade_downgrade_upgrade(test_engine):
    """Verify baseline migration upgrade -> downgrade -> upgrade completes cleanly
    and restores all schema objects for the identity & elder assignment tables.

    Validates: Requirement 16.5, 16.6
    """
    # Start fresh
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    # Upgrade to head
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Verify we're at the baseline revision
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert version == _HEAD_REVISION

    # Downgrade through every revision to base (drops the whole schema).
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_downgrade, "base")

    # Verify the schema is gone
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
            {"schema": SCHEMA_NAME},
        )
        assert result.first() is None, "eldercare_ai schema should not exist after downgrade"

    # Verify version is empty
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert version is None

    # Upgrade back to head
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Verify we're back at the baseline revision
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert version == _HEAD_REVISION

    # Verify all current-head tables (including our core 8) are restored.
    async with test_engine.begin() as conn:
        tables = await conn.run_sync(_get_tables)
    assert len(tables) == _TOTAL_HEAD_TABLE_COUNT
    assert set(_CORE_TABLES) <= set(tables)

    # Verify all indexes are restored
    expected_indexes = [
        "idx_actor_status",
        "uq_actor_email",
        "idx_membership_actor_active",
        "uq_membership_scope",
        "idx_elder_tenant_unit",
        "idx_relationship_elder_actor",
        "idx_assignment_worker_time",
        "idx_assignment_elder_time",
        "idx_outbox_pending",
        "uq_care_unit_name",
        "outbox_event_event_id_key",
    ]

    async with test_engine.begin() as conn:
        all_indexes: list[str] = []
        for table in _CORE_TABLES:
            indexes = await conn.run_sync(_get_indexes, table)
            all_indexes.extend(indexes)

    for idx in expected_indexes:
        assert (
            idx in all_indexes
        ), f"Expected index '{idx}' not restored after round-trip. Found: {all_indexes}"

    # Verify all check constraints are restored
    expected_checks = [
        "actor_status_check",
        "ck_membership_period",
        "care_unit_status_check",
        "elder_status_check",
        "ck_care_relationship_period",
        "ck_assignment_period",
        "tenant_status_check",
    ]

    async with test_engine.begin() as conn:
        all_checks: list[str] = []
        for table in _CORE_TABLES:
            checks = await conn.run_sync(_get_check_constraints, table)
            all_checks.extend(checks)

    for chk in expected_checks:
        assert (
            chk in all_checks
        ), f"Expected CHECK constraint '{chk}' not restored after round-trip. Found: {all_checks}"

    # Verify all foreign keys are restored
    expected_fks = [
        "care_unit_tenant_id_fkey",
        "actor_tenant_membership_actor_id_fkey",
        "actor_tenant_membership_care_unit_id_fkey",
        "actor_tenant_membership_tenant_id_fkey",
        "elder_tenant_id_fkey",
        "elder_primary_care_unit_id_fkey",
        "care_relationship_elder_id_fkey",
        "care_relationship_actor_id_fkey",
        "care_relationship_tenant_id_fkey",
        "care_relationship_care_unit_id_fkey",
        "care_assignment_tenant_id_fkey",
        "care_assignment_care_unit_id_fkey",
        "care_assignment_elder_id_fkey",
        "care_assignment_worker_actor_id_fkey",
        "outbox_event_tenant_id_fkey",
        "outbox_event_elder_id_fkey",
        "outbox_event_actor_id_fkey",
    ]

    async with test_engine.begin() as conn:
        all_fks: list[str] = []
        for table in _CORE_TABLES:
            fks = await conn.run_sync(_get_foreign_keys, table)
            all_fks.extend(fks)

    for fk in expected_fks:
        assert (
            fk in all_fks
        ), f"Expected FK constraint '{fk}' not restored after round-trip. Found: {all_fks}"


@pytest.mark.asyncio
async def test_baseline_full_downgrade_to_base(test_engine):
    """Verify downgrading from head all the way to base removes everything.

    Validates: Requirement 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    # Upgrade to head
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Downgrade to base (removes all migrations)
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_downgrade, "base")

    # Verify no application tables remain
    async with test_engine.begin() as conn:
        tables = await conn.run_sync(_get_tables)
        assert tables == [], f"Expected no tables after downgrade to base, got {tables}"

    # Verify the eldercare_ai schema itself is gone
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
            {"schema": SCHEMA_NAME},
        )
        assert (
            result.first() is None
        ), "eldercare_ai schema should not exist after downgrade to base"

    # Verify alembic_version is empty
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert version is None, f"Expected no version after downgrade to base, got '{version}'"
