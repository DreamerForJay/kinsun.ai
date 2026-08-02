"""Tests for secret-safe container database configuration."""

from __future__ import annotations

from urllib.parse import quote

import pytest
from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from sqlalchemy.engine import make_url

from app.container_entrypoint import DatabaseConfigurationError, ensure_database_url


def _database_parts() -> dict[str, str]:
    return {
        "DB_HOST": "cluster.example.internal",
        "DB_PORT": "5432",
        "DB_NAME": "elder care/data",
        "DB_USERNAME": "service@user",
        "DB_PASSWORD": "not-a-real-secret:/?#[]@!$&'()*+,;=",
    }


def test_existing_database_url_is_preserved() -> None:
    environment = {"DATABASE_URL": "postgresql+asyncpg://existing.invalid/database"}

    result = ensure_database_url("postgresql+asyncpg", environment)

    assert result == "postgresql+asyncpg://existing.invalid/database"
    assert environment["DATABASE_URL"] == result


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+asyncpg://existing.invalid/database",
        "postgresql://existing.invalid/database",
        "not-a-database-url",
    ],
)
def test_existing_database_url_with_wrong_driver_fails_closed(database_url: str) -> None:
    environment = {"DATABASE_URL": database_url}

    with pytest.raises(DatabaseConfigurationError, match="driver"):
        ensure_database_url("postgresql+psycopg", environment)

    assert environment["DATABASE_URL"] == database_url


@pytest.mark.parametrize(
    ("driver", "query_key"),
    [
        ("postgresql+asyncpg", "ssl"),
        ("postgresql+psycopg", "sslmode"),
    ],
)
def test_explicit_staging_tls_uses_driver_specific_option(driver: str, query_key: str) -> None:
    environment = _database_parts() | {"DB_SSLMODE": "require"}

    result = ensure_database_url(driver, environment)

    assert result.endswith(f"?{query_key}=require")


def test_asyncpg_tls_url_is_accepted_by_sqlalchemy_dialect() -> None:
    environment = _database_parts() | {"DB_SSLMODE": "require"}
    database_url = ensure_database_url("postgresql+asyncpg", environment)

    _, connect_options = PGDialect_asyncpg().create_connect_args(make_url(database_url))

    assert connect_options["ssl"] == "require"
    assert "sslmode" not in connect_options


def test_psycopg_tls_url_is_accepted_by_sqlalchemy_dialect() -> None:
    environment = _database_parts() | {"DB_SSLMODE": "require"}
    database_url = ensure_database_url("postgresql+psycopg", environment)

    _, connect_options = PGDialect_psycopg().create_connect_args(make_url(database_url))

    assert connect_options["sslmode"] == "require"


@pytest.mark.parametrize("ssl_mode", ["disable", "allow", "prefer", "verify-ca"])
def test_explicit_non_required_tls_mode_fails_closed(ssl_mode: str) -> None:
    environment = _database_parts() | {"DB_SSLMODE": ssl_mode}

    with pytest.raises(DatabaseConfigurationError, match="DB_SSLMODE"):
        ensure_database_url("postgresql+asyncpg", environment)

    assert "DATABASE_URL" not in environment


def test_conflicting_existing_tls_option_fails_closed() -> None:
    environment = {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@db.invalid/app?ssl=disable",
        "DB_SSLMODE": "require",
    }

    with pytest.raises(DatabaseConfigurationError, match="conflicting TLS"):
        ensure_database_url("postgresql+asyncpg", environment)


@pytest.mark.parametrize(
    ("driver", "expected_scheme"),
    [
        ("postgresql+asyncpg", "postgresql+asyncpg://"),
        ("postgresql+psycopg", "postgresql+psycopg://"),
    ],
)
def test_url_is_built_for_each_container_driver(driver: str, expected_scheme: str) -> None:
    environment = _database_parts()

    result = ensure_database_url(driver, environment)

    assert result.startswith(expected_scheme)
    assert quote(environment["DB_USERNAME"], safe="") in result
    assert quote(environment["DB_PASSWORD"], safe="") in result
    assert result.endswith(f"/{quote(environment['DB_NAME'], safe='')}")
    assert environment["DATABASE_URL"] == result
    assert environment["DB_PASSWORD"] not in result


def test_ipv6_host_is_bracketed() -> None:
    environment = _database_parts() | {"DB_HOST": "2001:db8::1"}

    result = ensure_database_url("postgresql+asyncpg", environment)

    assert "@[2001:db8::1]:5432/" in result


def test_missing_component_fails_without_exposing_other_values() -> None:
    environment = _database_parts()
    password = environment.pop("DB_PASSWORD")

    with pytest.raises(DatabaseConfigurationError) as exc_info:
        ensure_database_url("postgresql+asyncpg", environment)

    assert "DB_PASSWORD" in str(exc_info.value)
    assert password not in str(exc_info.value)
    assert "DATABASE_URL" not in environment


@pytest.mark.parametrize("port", ["not-a-number", "0", "65536"])
def test_invalid_port_fails_closed(port: str) -> None:
    environment = _database_parts() | {"DB_PORT": port}

    with pytest.raises(DatabaseConfigurationError, match="DB_PORT"):
        ensure_database_url("postgresql+psycopg", environment)

    assert "DATABASE_URL" not in environment


def test_unsupported_driver_fails_closed() -> None:
    with pytest.raises(DatabaseConfigurationError, match="Unsupported database driver"):
        ensure_database_url("postgresql", _database_parts())
