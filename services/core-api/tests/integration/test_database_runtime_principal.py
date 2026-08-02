"""PostgreSQL 16 integration proof for the Core runtime principal."""

from __future__ import annotations

import os
from urllib.parse import quote

import psycopg
import pytest
from psycopg import sql

from app.database_runtime_principal import (
    RUNTIME_USERNAME,
    RuntimeCredential,
    reconcile_runtime_principal,
)

_DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun_test"
)
_RUNTIME_PASSWORD = "synthetic-integration-runtime-password-000000000001"
_CURRENT_TABLE = "runtime_principal_current_probe"
_FUTURE_TABLE = "runtime_principal_future_probe"
_CURRENT_TYPE = "runtime_principal_current_state"
_FUTURE_TYPE = "runtime_principal_future_state"


def _admin_urls() -> tuple[str, str]:
    async_url = os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)
    sqlalchemy_url = async_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    psycopg_url = sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://")
    return sqlalchemy_url, psycopg_url


def _runtime_url(admin_psycopg_url: str) -> str:
    authority_and_path = admin_psycopg_url.split("@", 1)[1]
    return (
        f"postgresql://{quote(RUNTIME_USERNAME, safe='')}:"
        f"{quote(_RUNTIME_PASSWORD, safe='')}@{authority_and_path}"
    )


def _drop_probes(cursor: psycopg.Cursor) -> None:
    cursor.execute(f'DROP TABLE IF EXISTS eldercare_ai."{_FUTURE_TABLE}"')
    cursor.execute(f'DROP TABLE IF EXISTS eldercare_ai."{_CURRENT_TABLE}"')
    cursor.execute(f'DROP TYPE IF EXISTS eldercare_ai."{_FUTURE_TYPE}"')
    cursor.execute(f'DROP TYPE IF EXISTS eldercare_ai."{_CURRENT_TYPE}"')


def _runtime_role_exists(cursor: psycopg.Cursor) -> bool:
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
        (RUNTIME_USERNAME,),
    )
    return bool(cursor.fetchone()[0])


def _drop_test_runtime_role(cursor: psycopg.Cursor) -> None:
    """Remove grants and the cluster-wide role created by this isolated test."""
    cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(RUNTIME_USERNAME)))
    cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(RUNTIME_USERNAME)))


@pytest.mark.usefixtures("run_migrations")
def test_runtime_role_has_dml_and_sequence_access_but_no_schema_ddl() -> None:
    sqlalchemy_admin_url, psycopg_admin_url = _admin_urls()
    role_created_by_test = False

    with psycopg.connect(psycopg_admin_url) as admin_connection:
        with admin_connection.cursor() as cursor:
            if _runtime_role_exists(cursor):
                pytest.skip(
                    "runtime-principal integration requires an isolated cluster "
                    "without a pre-existing kinsun_app role"
                )

    try:
        with psycopg.connect(psycopg_admin_url) as admin_connection:
            with admin_connection.cursor() as cursor:
                _drop_probes(cursor)
                cursor.execute(f"CREATE TYPE eldercare_ai.\"{_CURRENT_TYPE}\" AS ENUM ('ready')")
                cursor.execute(
                    f"""
                    CREATE TABLE eldercare_ai."{_CURRENT_TABLE}" (
                        id bigserial PRIMARY KEY,
                        value text NOT NULL,
                        state eldercare_ai."{_CURRENT_TYPE}" NOT NULL
                    )
                    """
                )

        reconcile_runtime_principal(
            sqlalchemy_admin_url,
            RuntimeCredential(RUNTIME_USERNAME, _RUNTIME_PASSWORD),
        )
        role_created_by_test = True

        # Objects created after reconciliation must receive the same least-privilege
        # grants through ALTER DEFAULT PRIVILEGES.
        with psycopg.connect(psycopg_admin_url) as admin_connection:
            with admin_connection.cursor() as cursor:
                cursor.execute(f"CREATE TYPE eldercare_ai.\"{_FUTURE_TYPE}\" AS ENUM ('ready')")
                cursor.execute(
                    f"""
                    CREATE TABLE eldercare_ai."{_FUTURE_TABLE}" (
                        id bigserial PRIMARY KEY,
                        value text NOT NULL,
                        state eldercare_ai."{_FUTURE_TYPE}" NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    SELECT rolsuper, rolcreatedb, rolcreaterole, rolinherit,
                           rolreplication, rolbypassrls
                      FROM pg_roles
                     WHERE rolname = %s
                    """,
                    (RUNTIME_USERNAME,),
                )
                assert cursor.fetchone() == (False, False, False, False, False, False)
                cursor.execute(
                    "SELECT has_schema_privilege(%s, 'eldercare_ai', 'USAGE'), "
                    "has_schema_privilege(%s, 'eldercare_ai', 'CREATE')",
                    (RUNTIME_USERNAME, RUNTIME_USERNAME),
                )
                assert cursor.fetchone() == (True, False)

        with psycopg.connect(_runtime_url(psycopg_admin_url)) as runtime_connection:
            with runtime_connection.cursor() as cursor:
                for table_name in (_CURRENT_TABLE, _FUTURE_TABLE):
                    cursor.execute(
                        f"""
                        INSERT INTO eldercare_ai."{table_name}" (value, state)
                        VALUES (%s, 'ready') RETURNING id
                        """,
                        ("synthetic",),
                    )
                    row_id = cursor.fetchone()[0]
                    cursor.execute(
                        f'UPDATE eldercare_ai."{table_name}" SET value = %s WHERE id = %s',
                        ("updated", row_id),
                    )
                    cursor.execute(
                        f'SELECT value FROM eldercare_ai."{table_name}" WHERE id = %s',
                        (row_id,),
                    )
                    assert cursor.fetchone() == ("updated",)
                    cursor.execute(
                        f'DELETE FROM eldercare_ai."{table_name}" WHERE id = %s',
                        (row_id,),
                    )
            runtime_connection.commit()

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime_connection.cursor() as cursor:
                    cursor.execute("CREATE TABLE eldercare_ai.runtime_principal_forbidden (id int)")
            runtime_connection.rollback()

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime_connection.cursor() as cursor:
                    cursor.execute(f'TRUNCATE eldercare_ai."{_CURRENT_TABLE}"')
            runtime_connection.rollback()
    finally:
        with psycopg.connect(psycopg_admin_url) as admin_connection:
            with admin_connection.cursor() as cursor:
                _drop_probes(cursor)
                if role_created_by_test and _runtime_role_exists(cursor):
                    _drop_test_runtime_role(cursor)
