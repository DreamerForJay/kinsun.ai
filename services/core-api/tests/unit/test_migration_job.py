"""Tests for the one-shot Alembic plus runtime-principal job."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from app import migration_job
from app.database_runtime_principal import RUNTIME_USERNAME, RuntimeCredential

ADMIN_PASSWORD = "synthetic-admin-password-value"
RUNTIME_PASSWORD = "synthetic-runtime-password-material-000000000001"


def _environment() -> dict[str, str]:
    return {
        "DB_HOST": "cluster.example.internal",
        "DB_PORT": "5432",
        "DB_NAME": "kinsun",
        "DB_USERNAME": "kinsun_admin",
        "DB_PASSWORD": ADMIN_PASSWORD,
        "DB_SSLMODE": "require",
        "DB_RUNTIME_USERNAME": RUNTIME_USERNAME,
        "DB_RUNTIME_PASSWORD": RUNTIME_PASSWORD,
    }


def test_alembic_completes_before_runtime_principal_and_child_does_not_receive_runtime_secret() -> (
    None
):
    calls: list[tuple[str, object]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(("alembic", (command, kwargs)))
        assert kwargs["check"] is True
        assert kwargs["env"]["DATABASE_URL"].endswith("?sslmode=require")
        assert "DB_RUNTIME_USERNAME" not in kwargs["env"]
        assert "DB_RUNTIME_PASSWORD" not in kwargs["env"]
        return subprocess.CompletedProcess(command, 0)

    def fake_reconcile(database_url: str, credential: RuntimeCredential) -> None:
        calls.append(("reconcile", (database_url, credential)))

    migration_job.run_migration_job(_environment(), run_command=fake_run, reconcile=fake_reconcile)

    assert [name for name, _ in calls] == ["alembic", "reconcile"]
    database_url, credential = calls[1][1]
    assert isinstance(database_url, str)
    assert database_url.endswith("?sslmode=require")
    assert isinstance(credential, RuntimeCredential)
    assert credential.username == RUNTIME_USERNAME


def test_alembic_failure_prevents_runtime_principal_reconciliation() -> None:
    reconciled = False

    def failed_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, command)

    def fake_reconcile(database_url: str, credential: RuntimeCredential) -> None:
        nonlocal reconciled
        reconciled = True

    with pytest.raises(subprocess.CalledProcessError):
        migration_job.run_migration_job(
            _environment(), run_command=failed_run, reconcile=fake_reconcile
        )

    assert reconciled is False


def test_invalid_runtime_secret_prevents_alembic() -> None:
    invoked = False
    environment = _environment() | {"DB_RUNTIME_USERNAME": "kinsun_admin"}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal invoked
        invoked = True
        return subprocess.CompletedProcess(command, 0)

    with pytest.raises(ValueError, match="DB_RUNTIME_USERNAME"):
        migration_job.run_migration_job(environment, run_command=fake_run)

    assert invoked is False


def test_main_error_output_never_echoes_nested_secret(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def fail() -> None:
        raise RuntimeError(f"driver failure contained {RUNTIME_PASSWORD}")

    monkeypatch.setattr(migration_job, "run_migration_job", fail)

    with pytest.raises(SystemExit) as exc_info:
        migration_job.main([])

    output = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "runtime-principal reconciliation failed" in output.err
    assert RUNTIME_PASSWORD not in output.err
