"""Container entrypoint that prepares a database URL without logging secrets."""

from __future__ import annotations

import os
import sys
from collections.abc import MutableMapping, Sequence
from typing import NoReturn
from urllib.parse import parse_qsl, quote

_SUPPORTED_DRIVERS = frozenset({"postgresql+asyncpg", "postgresql+psycopg"})
_DATABASE_COMPONENTS = (
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USERNAME",
    "DB_PASSWORD",
)


class DatabaseConfigurationError(ValueError):
    """Raised when runtime database environment variables are incomplete."""


def _enforce_configured_tls(
    driver: str,
    database_url: str,
    target: MutableMapping[str, str],
) -> str:
    """Add the driver-specific TLS option when staging requests it.

    SQLAlchemy passes URL query options directly to asyncpg, whose keyword is
    ``ssl``.  Psycopg/libpq uses ``sslmode``.  Local development remains unchanged
    when ``DB_SSLMODE`` is absent, while an explicit but weaker mode fails closed.
    """
    ssl_mode = target.get("DB_SSLMODE", "").strip()
    if not ssl_mode:
        return database_url
    if ssl_mode != "require":
        raise DatabaseConfigurationError("DB_SSLMODE must be require when configured")

    expected_key = "ssl" if driver == "postgresql+asyncpg" else "sslmode"
    query = database_url.partition("?")[2]
    ssl_options = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key in {"ssl", "sslmode"}
    ]
    if ssl_options:
        if ssl_options != [(expected_key, "require")]:
            raise DatabaseConfigurationError("DATABASE_URL contains conflicting TLS options")
        return database_url

    separator = "&" if "?" in database_url else "?"
    return f"{database_url}{separator}{expected_key}=require"


def _validate_database_url_driver(driver: str, database_url: str) -> None:
    """Require an existing URL to use the container's exact SQLAlchemy driver."""
    configured_driver, separator, _ = database_url.partition("://")
    if not separator or configured_driver != driver:
        raise DatabaseConfigurationError("DATABASE_URL driver does not match container driver")


def ensure_database_url(
    driver: str,
    environ: MutableMapping[str, str] | None = None,
) -> str:
    """Return and export ``DATABASE_URL``, constructing it only when absent.

    AWS ECS injects the Aurora username and password as separate secret-backed
    environment variables. Values are percent-encoded here so credentials never
    need to be interpolated by IaC or a shell.
    """
    if driver not in _SUPPORTED_DRIVERS:
        raise DatabaseConfigurationError("Unsupported database driver")

    target = os.environ if environ is None else environ
    existing = target.get("DATABASE_URL", "")
    if existing.strip():
        _validate_database_url_driver(driver, existing)
        database_url = _enforce_configured_tls(driver, existing, target)
        target["DATABASE_URL"] = database_url
        return database_url

    missing = [name for name in _DATABASE_COMPONENTS if not target.get(name)]
    if missing:
        raise DatabaseConfigurationError(
            f"Missing required database environment variables: {', '.join(missing)}"
        )

    host = target["DB_HOST"].strip()
    if (
        not host
        or any(character in host for character in "/@?#")
        or any(character.isspace() for character in host)
    ):
        raise DatabaseConfigurationError("DB_HOST is invalid")

    try:
        port = int(target["DB_PORT"])
    except ValueError as exc:
        raise DatabaseConfigurationError("DB_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise DatabaseConfigurationError("DB_PORT must be between 1 and 65535")

    # Bracket an IPv6 literal, while leaving an already bracketed literal alone.
    if ":" in host and not (host.startswith("[") and host.endswith("]")):
        host = f"[{host}]"

    username = quote(target["DB_USERNAME"], safe="")
    password = quote(target["DB_PASSWORD"], safe="")
    database = quote(target["DB_NAME"], safe="")
    database_url = f"{driver}://{username}:{password}@{host}:{port}/{database}"
    database_url = _enforce_configured_tls(driver, database_url, target)
    target["DATABASE_URL"] = database_url
    return database_url


def main(argv: Sequence[str] | None = None) -> NoReturn:
    """Prepare configuration and replace this process with the requested command."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) < 2:
        print("FATAL: entrypoint requires a database driver and command", file=sys.stderr)
        raise SystemExit(64)

    driver, *command = arguments
    try:
        ensure_database_url(driver)
    except DatabaseConfigurationError as exc:
        # Exception messages contain only configuration field names, never values.
        print(f"FATAL: database configuration invalid: {exc}", file=sys.stderr)
        raise SystemExit(78) from exc

    os.execvp(command[0], command)
    raise AssertionError("os.execvp returned unexpectedly")


if __name__ == "__main__":
    main()
