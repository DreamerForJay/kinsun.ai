"""One-shot staging database migration and runtime-principal reconciliation."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, MutableMapping, Sequence

from app.container_entrypoint import ensure_database_url
from app.database_runtime_principal import (
    RuntimeCredential,
    load_runtime_credential,
    reconcile_runtime_principal,
)


def run_migration_job(
    environ: MutableMapping[str, str] | None = None,
    *,
    run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    reconcile: Callable[[str, RuntimeCredential], None] = reconcile_runtime_principal,
) -> None:
    """Validate both credentials, migrate as admin, then provision the runtime role."""
    target = os.environ if environ is None else environ
    runtime_credential = load_runtime_credential(target)
    admin_database_url = ensure_database_url("postgresql+psycopg", target)

    # Alembic requires only the admin URL.  Do not unnecessarily pass the runtime
    # password into its child-process environment.
    alembic_environment = dict(target)
    alembic_environment.pop("DB_RUNTIME_USERNAME", None)
    alembic_environment.pop("DB_RUNTIME_PASSWORD", None)
    run_command(["alembic", "upgrade", "head"], check=True, env=alembic_environment)
    reconcile(admin_database_url, runtime_credential)


def main(argv: Sequence[str] | None = None) -> None:
    """Run once and emit only fixed, secret-independent status messages."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("FATAL: migration job does not accept arguments", file=sys.stderr)
        raise SystemExit(64)

    try:
        run_migration_job()
    except Exception as exc:
        # Never include exception text: DB drivers and subprocesses may carry connection data.
        print("FATAL: migration or runtime-principal reconciliation failed", file=sys.stderr)
        raise SystemExit(1) from exc

    print("Migration and runtime-principal reconciliation completed")


if __name__ == "__main__":
    main()
