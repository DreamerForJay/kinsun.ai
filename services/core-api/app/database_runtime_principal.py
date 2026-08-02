"""Reconcile the least-privilege PostgreSQL principal used by Core API.

This module is intentionally migration-only.  The long-lived API container never
receives the Aurora administrator credential and cannot call this code successfully.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import psycopg
from psycopg import sql

RUNTIME_SCHEMA = "eldercare_ai"
RUNTIME_USERNAME = "kinsun_app"
_RUNTIME_USERNAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_PROVISIONING_LOCK_ID = 5_409_566_445_540_616_549


class RuntimePrincipalConfigurationError(ValueError):
    """Raised when injected runtime credentials violate the staging contract."""


class RuntimePrincipalInvariantError(RuntimeError):
    """Raised when an existing role cannot be reconciled without privilege risk."""


@dataclass(frozen=True)
class RuntimeCredential:
    """Credential material whose representation never includes the password."""

    username: str
    password: str = field(repr=False)


class _PgConnection(Protocol):
    pgconn: Any

    def __enter__(self) -> _PgConnection: ...

    def __exit__(self, *args: object) -> None: ...

    def cursor(self) -> Any: ...


def load_runtime_credential(environ: Mapping[str, str] | None = None) -> RuntimeCredential:
    """Load and validate the separately injected runtime credential.

    The username is deliberately fixed for staging.  Accepting an arbitrary identifier
    from a mutable secret would make a mistaken secret update capable of targeting the
    administrator role.  Password validation errors mention field names only.
    """
    source = os.environ if environ is None else environ
    username = source.get("DB_RUNTIME_USERNAME", "")
    password = source.get("DB_RUNTIME_PASSWORD", "")

    if not username or not _RUNTIME_USERNAME_PATTERN.fullmatch(username):
        raise RuntimePrincipalConfigurationError("DB_RUNTIME_USERNAME is invalid")
    if username != RUNTIME_USERNAME:
        raise RuntimePrincipalConfigurationError("DB_RUNTIME_USERNAME is not the staging role")
    if not 32 <= len(password) <= 1024 or "\x00" in password:
        raise RuntimePrincipalConfigurationError("DB_RUNTIME_PASSWORD is invalid")

    return RuntimeCredential(username=username, password=password)


def _assert_existing_role_is_safe(cursor: Any, username: str) -> None:
    """Reject roles carrying membership or ownership that could imply DDL authority."""
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM pg_auth_members memberships
              JOIN pg_roles members ON members.oid = memberships.member
              JOIN pg_roles granted_roles ON granted_roles.oid = memberships.roleid
             WHERE members.rolname = %s
                OR granted_roles.rolname = %s
        )
        """,
        (username, username),
    )
    if cursor.fetchone()[0]:
        raise RuntimePrincipalInvariantError("runtime role has unexpected role membership")

    cursor.execute(
        """
        WITH runtime_role AS (
            SELECT oid FROM pg_roles WHERE rolname = %s
        )
        SELECT EXISTS (
            SELECT 1 FROM pg_database, runtime_role
             WHERE datname = current_database() AND datdba = runtime_role.oid
            UNION ALL
            SELECT 1 FROM pg_namespace, runtime_role
             WHERE nspowner = runtime_role.oid
            UNION ALL
            SELECT 1 FROM pg_class, runtime_role
             WHERE relowner = runtime_role.oid
            UNION ALL
            SELECT 1 FROM pg_proc, runtime_role
             WHERE proowner = runtime_role.oid
            UNION ALL
            SELECT 1 FROM pg_type, runtime_role
             WHERE typowner = runtime_role.oid
        )
        """,
        (username,),
    )
    if cursor.fetchone()[0]:
        raise RuntimePrincipalInvariantError("runtime role unexpectedly owns database objects")


def _password_verifier(connection: _PgConnection, credential: RuntimeCredential) -> str:
    """Create a SCRAM verifier locally so the cleartext password is never SQL text."""
    verifier = connection.pgconn.encrypt_password(
        credential.password.encode("utf-8"),
        credential.username.encode("utf-8"),
        b"scram-sha-256",
    )
    if not verifier:
        raise RuntimePrincipalInvariantError("could not create runtime password verifier")
    return verifier.decode("ascii")


def _execute_role_reconciliation(
    connection: _PgConnection,
    cursor: Any,
    credential: RuntimeCredential,
    *,
    role_exists: bool,
    admin_username: str,
    database_name: str,
) -> None:
    """Apply role attributes and current/future object privileges transactionally."""
    role = sql.Identifier(credential.username)
    schema = sql.Identifier(RUNTIME_SCHEMA)
    database = sql.Identifier(database_name)
    admin = sql.Identifier(admin_username)
    password_verifier = sql.Literal(_password_verifier(connection, credential))

    role_verb = sql.SQL("ALTER ROLE") if role_exists else sql.SQL("CREATE ROLE")
    cursor.execute(
        sql.SQL(
            "{} {} WITH LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS"
        ).format(role_verb, role, password_verifier)
    )
    cursor.execute(
        sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path TO {}, public").format(
            role, database, schema
        )
    )

    # Remove stale explicit privileges before granting the exact runtime set.  PostgreSQL DDL
    # is transactional, so any later failure rolls this entire reconciliation back.
    cursor.execute(sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(database, role))
    cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role))
    cursor.execute(sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA {} FROM {}").format(schema, role))
    cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, role))

    for object_type in ("TABLES", "SEQUENCES", "FUNCTIONS"):
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON ALL {} IN SCHEMA {} FROM {}").format(
                sql.SQL(object_type), schema, role
            )
        )
    cursor.execute(
        sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}").format(
            schema, role
        )
    )
    cursor.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(schema, role)
    )
    # PostgreSQL has no GRANT/REVOKE ``ON ALL TYPES IN SCHEMA`` syntax for existing
    # objects.  Enumerate only user-defined enum/domain types and quote every identifier.
    cursor.execute(
        """
        SELECT types.typname
          FROM pg_type AS types
          JOIN pg_namespace AS namespaces ON namespaces.oid = types.typnamespace
         WHERE namespaces.nspname = %s
           AND types.typtype IN ('d', 'e')
         ORDER BY types.typname
        """,
        (RUNTIME_SCHEMA,),
    )
    for (type_name,) in cursor.fetchall():
        type_identifier = sql.Identifier(RUNTIME_SCHEMA, type_name)
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON TYPE {} FROM {}").format(type_identifier, role)
        )
        cursor.execute(sql.SQL("GRANT USAGE ON TYPE {} TO {}").format(type_identifier, role))

    for object_type in ("TABLES", "SEQUENCES", "FUNCTIONS", "TYPES"):
        cursor.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
                "REVOKE ALL PRIVILEGES ON {} FROM {}"
            ).format(admin, schema, sql.SQL(object_type), role)
        )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(admin, schema, role)
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
            "GRANT USAGE, SELECT ON SEQUENCES TO {}"
        ).format(admin, schema, role)
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT USAGE ON TYPES TO {}"
        ).format(admin, schema, role)
    )


def reconcile_runtime_principal(
    admin_database_url: str,
    credential: RuntimeCredential,
    *,
    connect: Callable[[str], _PgConnection] = psycopg.connect,
) -> None:
    """Create/update the runtime LOGIN role after Alembic reaches head.

    The connection is the migration-only administrator connection.  No exception is logged
    here because driver exceptions can contain connection metadata; the outer one-shot job
    emits a fixed error message instead.
    """
    if not admin_database_url.startswith("postgresql+psycopg://"):
        raise RuntimePrincipalConfigurationError("administrator database URL driver is invalid")
    psycopg_dsn = admin_database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    with connect(psycopg_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_PROVISIONING_LOCK_ID,))
            cursor.execute("SELECT current_user, current_database()")
            admin_username, database_name = cursor.fetchone()
            if admin_username == credential.username:
                raise RuntimePrincipalInvariantError(
                    "administrator and runtime roles are identical"
                )

            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)",
                (RUNTIME_SCHEMA,),
            )
            if not cursor.fetchone()[0]:
                raise RuntimePrincipalInvariantError(
                    "runtime schema does not exist after migration"
                )

            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
                (credential.username,),
            )
            role_exists = cursor.fetchone()[0]
            if role_exists:
                _assert_existing_role_is_safe(cursor, credential.username)

            # Disabling statement logging in this transaction is defense in depth: the only
            # password-derived value sent as SQL is a SCRAM verifier, never cleartext.
            cursor.execute("SET LOCAL log_statement = 'none'")
            _execute_role_reconciliation(
                connection,
                cursor,
                credential,
                role_exists=role_exists,
                admin_username=admin_username,
                database_name=database_name,
            )
