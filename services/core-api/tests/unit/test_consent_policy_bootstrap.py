"""Safety and idempotency tests for the staging consent-policy bootstrap."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from app import consent_policy_bootstrap as bootstrap


class FakeCursor:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, object]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: object = None) -> None:
        self.executions.append((query, params))

    def fetchall(self) -> list[Mapping[str, Any]]:
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self, *, row_factory: Any) -> FakeCursor:
        assert row_factory is bootstrap.dict_row
        return self._cursor


class FakeConnector:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self.cursor = FakeCursor(rows)
        self.received_dsn: str | None = None

    def __call__(self, database_dsn: str) -> FakeConnection:
        self.received_dsn = database_dsn
        return FakeConnection(self.cursor)


def _environment(**overrides: str) -> dict[str, str]:
    return {
        "APP_ENV": "staging",
        "CONSENT_POLICY_VERSION": "demo-consent-v1",
        "DATABASE_URL": "postgresql+psycopg://user:not-a-secret@db.invalid/kinsun",
    } | overrides


def _config() -> bootstrap.BootstrapConfig:
    return bootstrap.load_config(_environment())


def _expected_row(**overrides: object) -> dict[str, object]:
    return {
        "owner_tenant_id": None,
        "policy_code": bootstrap.POLICY_CODE,
        "policy_type": bootstrap.POLICY_TYPE,
        "version": "demo-consent-v1",
        "status": bootstrap.POLICY_STATUS,
        "source_version_id": None,
        "policy_payload": bootstrap.desired_policy_payload(),
        "effective_from": None,
        "effective_to": None,
        "approved_by_actor_id": None,
    } | overrides


@pytest.mark.parametrize("app_env", ["production", "development", "", "PRODUCTION"])
def test_only_staging_environment_is_allowed(app_env: str) -> None:
    with pytest.raises(bootstrap.BootstrapConfigurationError, match="APP_ENV"):
        bootstrap.load_config(_environment(APP_ENV=app_env))


@pytest.mark.parametrize(
    "version",
    ["", "contains spaces", "UPPERCASE", "x" * 41, "../policy"],
)
def test_policy_version_must_be_explicit_and_safe(version: str) -> None:
    with pytest.raises(bootstrap.BootstrapConfigurationError, match="CONSENT_POLICY_VERSION"):
        bootstrap.load_config(_environment(CONSENT_POLICY_VERSION=version))


def test_database_dsn_is_hidden_from_config_representation() -> None:
    config = _config()

    assert config.database_dsn.startswith("postgresql://")
    assert "not-a-secret" not in repr(config)


def test_absent_version_is_created_once_with_unsigned_synthetic_content() -> None:
    connector = FakeConnector([])

    action = bootstrap.reconcile_consent_policy(_config(), connect=connector)

    assert action is bootstrap.BootstrapAction.CREATED
    assert connector.received_dsn == _config().database_dsn
    assert "pg_advisory_xact_lock" in connector.cursor.executions[0][0]
    assert "LOCK TABLE eldercare_ai.policy_registry" in connector.cursor.executions[1][0]
    insert_query, insert_params = connector.cursor.executions[-1]
    assert "INSERT INTO eldercare_ai.policy_registry" in insert_query
    assert insert_params is not None
    serialized_payload = insert_params[-1]  # type: ignore[index]
    assert json.loads(serialized_payload) == bootstrap.desired_policy_payload()
    assert bootstrap.PRODUCTION_APPROVED is False
    assert bootstrap.desired_policy_payload()["synthetic_only"] is True


def test_exact_existing_policy_is_idempotently_left_unchanged() -> None:
    connector = FakeConnector([_expected_row()])

    action = bootstrap.reconcile_consent_policy(_config(), connect=connector)

    assert action is bootstrap.BootstrapAction.UNCHANGED
    assert all("INSERT INTO" not in query for query, _ in connector.cursor.executions)


@pytest.mark.parametrize(
    "row",
    [
        _expected_row(policy_payload={"synthetic_only": True}),
        _expected_row(status="DRAFT"),
        _expected_row(owner_tenant_id="10000000-0000-4000-8000-000000000001"),
        _expected_row(approved_by_actor_id="20000000-0000-4000-8000-000000000001"),
    ],
)
def test_existing_same_version_with_any_difference_fails_closed(row: dict[str, object]) -> None:
    connector = FakeConnector([row])

    with pytest.raises(bootstrap.ExistingPolicyMismatchError):
        bootstrap.reconcile_consent_policy(_config(), connect=connector)

    assert all("INSERT INTO" not in query for query, _ in connector.cursor.executions)


def test_multiple_rows_for_same_version_fail_closed_even_if_one_matches() -> None:
    connector = FakeConnector([_expected_row(), _expected_row(policy_code="other")])

    with pytest.raises(bootstrap.ExistingPolicyMismatchError):
        bootstrap.reconcile_consent_policy(_config(), connect=connector)


def test_success_receipt_is_explicitly_non_production() -> None:
    receipt = bootstrap.build_receipt(_config(), bootstrap.BootstrapAction.CREATED)

    assert receipt["status"] == "SUCCESS"
    assert receipt["synthetic_only"] is True
    assert receipt["production_approved"] is False
    assert receipt["governance_status"] == "UNSIGNED_SYNTHETIC_STAGING_OVERRIDE"
    assert len(receipt["policy_payload_sha256"]) == 64  # type: ignore[arg-type]
    assert "database" not in receipt


def test_main_failure_never_logs_database_credentials(monkeypatch, capsys) -> None:
    secret = "credential-that-must-never-appear"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CONSENT_POLICY_VERSION", "demo-consent-v1")
    monkeypatch.setenv("DATABASE_URL", f"postgresql://user:{secret}@db.invalid/kinsun")

    with pytest.raises(SystemExit) as exit_info:
        bootstrap.main([])

    output = capsys.readouterr().out
    assert exit_info.value.code == 64
    assert secret not in output
    assert json.loads(output)["reason_code"] == "CONFIGURATION_INVALID"


def test_main_masks_driver_errors(monkeypatch, capsys) -> None:
    monkeypatch.setattr(bootstrap, "load_config", lambda: _config())

    def fail_with_sensitive_detail(config: bootstrap.BootstrapConfig) -> bootstrap.BootstrapAction:
        raise RuntimeError(f"database failure: {config.database_dsn}")

    monkeypatch.setattr(bootstrap, "reconcile_consent_policy", fail_with_sensitive_detail)

    with pytest.raises(SystemExit) as exit_info:
        bootstrap.main([])

    output = capsys.readouterr().out
    assert exit_info.value.code == 1
    assert "not-a-secret" not in output
    assert json.loads(output)["reason_code"] == "DATABASE_OPERATION_FAILED"
