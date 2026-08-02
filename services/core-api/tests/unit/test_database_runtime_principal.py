"""Tests for the fail-closed staging PostgreSQL runtime principal."""

from __future__ import annotations

from typing import Any

import pytest

from app.database_runtime_principal import (
    RUNTIME_USERNAME,
    RuntimeCredential,
    RuntimePrincipalConfigurationError,
    RuntimePrincipalInvariantError,
    load_runtime_credential,
    reconcile_runtime_principal,
)

RUNTIME_PASSWORD = "synthetic-runtime-password-material-000000000001"


class _FakePgConnection:
    def encrypt_password(
        self, password: bytes, username: bytes, algorithm: bytes | None = None
    ) -> bytes:
        assert password == RUNTIME_PASSWORD.encode()
        assert username == RUNTIME_USERNAME.encode()
        assert algorithm == b"scram-sha-256"
        return b"SCRAM-SHA-256$synthetic-verifier-only"


class _FakeCursor:
    def __init__(
        self,
        responses: list[tuple[Any, ...]],
        type_rows: list[tuple[str]] | None = None,
    ) -> None:
        self._responses = iter(responses)
        self._type_rows = [("consent_status",)] if type_rows is None else type_rows
        self.executions: list[tuple[str, object | None]] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: object, params: object | None = None) -> None:
        rendered = query.as_string() if hasattr(query, "as_string") else str(query)
        self.executions.append((rendered, params))

    def fetchone(self) -> tuple[Any, ...]:
        return next(self._responses)

    def fetchall(self) -> list[tuple[str]]:
        return self._type_rows


class _FakeConnection:
    def __init__(
        self,
        responses: list[tuple[Any, ...]],
        type_rows: list[tuple[str]] | None = None,
    ) -> None:
        self.pgconn = _FakePgConnection()
        self.cursor_instance = _FakeCursor(responses, type_rows)

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self.cursor_instance


def _credential() -> RuntimeCredential:
    return RuntimeCredential(RUNTIME_USERNAME, RUNTIME_PASSWORD)


def test_runtime_credential_is_fixed_and_password_is_redacted_from_repr() -> None:
    credential = load_runtime_credential(
        {
            "DB_RUNTIME_USERNAME": RUNTIME_USERNAME,
            "DB_RUNTIME_PASSWORD": RUNTIME_PASSWORD,
        }
    )

    assert credential.username == RUNTIME_USERNAME
    assert credential.password == RUNTIME_PASSWORD
    assert RUNTIME_PASSWORD not in repr(credential)


@pytest.mark.parametrize(
    "username",
    ["", "kinsun_admin", 'kinsun_app" SUPERUSER', "KINSUN_APP", "kinsun-app"],
)
def test_unexpected_or_unsafe_runtime_identifier_fails_closed(username: str) -> None:
    with pytest.raises(RuntimePrincipalConfigurationError, match="DB_RUNTIME_USERNAME"):
        load_runtime_credential(
            {"DB_RUNTIME_USERNAME": username, "DB_RUNTIME_PASSWORD": RUNTIME_PASSWORD}
        )


@pytest.mark.parametrize("password", ["", "too-short", "x" * 31, "x" * 1025, "x" * 32 + "\x00"])
def test_invalid_runtime_password_fails_without_echoing_value(password: str) -> None:
    with pytest.raises(RuntimePrincipalConfigurationError) as exc_info:
        load_runtime_credential(
            {"DB_RUNTIME_USERNAME": RUNTIME_USERNAME, "DB_RUNTIME_PASSWORD": password}
        )

    assert "DB_RUNTIME_PASSWORD" in str(exc_info.value)
    if password:
        assert password not in str(exc_info.value)


def test_new_role_is_created_with_only_current_and_future_dml_privileges() -> None:
    connection = _FakeConnection(
        [
            ('migration"owner', "kinsun"),
            (True,),  # eldercare_ai exists after Alembic
            (False,),  # runtime role is new
        ]
    )

    captured_dsn = ""

    def fake_connect(dsn: str) -> _FakeConnection:
        nonlocal captured_dsn
        captured_dsn = dsn
        return connection

    reconcile_runtime_principal(
        "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
        _credential(),
        connect=fake_connect,
    )

    assert captured_dsn == "postgresql://admin:never-log@db.invalid/kinsun"
    sql_text = "\n".join(query for query, _ in connection.cursor_instance.executions)
    assert RUNTIME_PASSWORD not in sql_text
    assert 'CREATE ROLE "kinsun_app" WITH LOGIN PASSWORD' in sql_text
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS" in sql_text
    assert 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "eldercare_ai"' in (
        sql_text
    )
    assert 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "eldercare_ai"' in sql_text
    assert 'GRANT USAGE ON TYPE "eldercare_ai"."consent_status" TO "kinsun_app"' in sql_text
    assert "ON ALL TYPES IN SCHEMA" not in sql_text
    assert 'FOR ROLE "migration""owner" IN SCHEMA "eldercare_ai"' in sql_text
    assert "GRANT CREATE" not in sql_text
    assert "GRANT TRUNCATE" not in sql_text
    assert "GRANT TRIGGER" not in sql_text
    assert "GRANT EXECUTE" not in sql_text


@pytest.mark.parametrize(
    ("safety_responses", "expected_message"),
    [
        ([(True,)], "membership"),
        ([(False,), (True,)], "owns"),
    ],
)
def test_existing_role_with_privilege_invariants_fails_before_alter(
    safety_responses: list[tuple[bool]], expected_message: str
) -> None:
    connection = _FakeConnection(
        [
            ("kinsun_admin", "kinsun"),
            (True,),
            (True,),  # runtime role already exists
            *safety_responses,
        ]
    )

    with pytest.raises(RuntimePrincipalInvariantError, match=expected_message):
        reconcile_runtime_principal(
            "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
            _credential(),
            connect=lambda _: connection,
        )

    sql_text = "\n".join(query for query, _ in connection.cursor_instance.executions)
    assert 'ALTER ROLE "kinsun_app"' not in sql_text
    assert RUNTIME_PASSWORD not in sql_text


def test_existing_role_membership_check_is_bidirectional() -> None:
    connection = _FakeConnection(
        [
            ("kinsun_admin", "kinsun"),
            (True,),
            (True,),  # runtime role already exists
            (False,),  # no membership in either direction
            (False,),  # no ownership
        ]
    )

    reconcile_runtime_principal(
        "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
        _credential(),
        connect=lambda _: connection,
    )

    membership_query, membership_params = connection.cursor_instance.executions[4]
    assert "memberships.member" in membership_query
    assert "memberships.roleid" in membership_query
    assert membership_params == (RUNTIME_USERNAME, RUNTIME_USERNAME)


def test_missing_schema_fails_before_role_creation() -> None:
    connection = _FakeConnection([("kinsun_admin", "kinsun"), (False,)])

    with pytest.raises(RuntimePrincipalInvariantError, match="schema does not exist"):
        reconcile_runtime_principal(
            "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
            _credential(),
            connect=lambda _: connection,
        )

    sql_text = "\n".join(query for query, _ in connection.cursor_instance.executions)
    assert "CREATE ROLE" not in sql_text


def test_admin_and_runtime_identity_collision_fails_closed() -> None:
    connection = _FakeConnection([(RUNTIME_USERNAME, "kinsun")])

    with pytest.raises(RuntimePrincipalInvariantError, match="identical"):
        reconcile_runtime_principal(
            "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
            _credential(),
            connect=lambda _: connection,
        )
