"""PostgreSQL round-trip for the one-shot staging consent-policy bootstrap."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from app import consent_policy_bootstrap as bootstrap

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun_test"
)


def test_bootstrap_is_idempotent_and_never_overwrites_existing_content() -> None:
    database_dsn = bootstrap._database_dsn(
        os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    )
    policy_version = f"it-{uuid4().hex}"
    config = bootstrap.BootstrapConfig(
        policy_version=policy_version,
        database_dsn=database_dsn,
    )

    try:
        assert bootstrap.reconcile_consent_policy(config) is bootstrap.BootstrapAction.CREATED
        assert bootstrap.reconcile_consent_policy(config) is bootstrap.BootstrapAction.UNCHANGED

        with psycopg.connect(database_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE eldercare_ai.policy_registry
                       SET policy_payload = '{"synthetic_only": true}'::jsonb
                     WHERE policy_type = %s AND version = %s
                    """,
                    (bootstrap.POLICY_TYPE, policy_version),
                )

        with pytest.raises(bootstrap.ExistingPolicyMismatchError):
            bootstrap.reconcile_consent_policy(config)

        with psycopg.connect(database_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT policy_payload
                      FROM eldercare_ai.policy_registry
                     WHERE policy_type = %s AND version = %s
                    """,
                    (bootstrap.POLICY_TYPE, policy_version),
                )
                assert cursor.fetchone()[0] == {"synthetic_only": True}
    finally:
        with psycopg.connect(database_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM eldercare_ai.policy_registry
                     WHERE policy_type = %s AND version = %s
                    """,
                    (bootstrap.POLICY_TYPE, policy_version),
                )
