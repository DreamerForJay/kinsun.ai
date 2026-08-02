"""One-shot synthetic consent-policy bootstrap for staging only.

This is deliberately separate from Alembic. Schema migrations describe database
structure; they must not silently approve or activate product policy content.
The command creates one unsigned, synthetic policy row only when the requested
version is entirely absent. Existing rows are compared exactly and are never
updated in place.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row

POLICY_CODE = "demo-consent-policy"
POLICY_TYPE = "CONSENT"
POLICY_STATUS = "ACTIVE"
GOVERNANCE_STATUS = "UNSIGNED_SYNTHETIC_STAGING_OVERRIDE"
PRODUCTION_APPROVED = False
SYNTHETIC_ONLY = True
CONSENT_POLICY_VERSION_ENV = "CONSENT_POLICY_VERSION"

_POLICY_VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")
_BOOTSTRAP_LOCK_ID = 5_106_861_415_591_492_712

SUPPORTED_PURPOSES = (
    "BASIC_VOICE",
    "TRANSCRIPT_STORAGE",
    "CARE_EVENT_EXTRACTION",
    "LONG_TERM_MEMORY",
    "COMPANION_SIGNAL_ANALYSIS",
    "PROACTIVE_COMPANION",
    "FAMILY_SHARING",
)


class BootstrapConfigurationError(ValueError):
    """Raised before database access when staging safeguards are incomplete."""


class ExistingPolicyMismatchError(RuntimeError):
    """Raised when the target version already has non-canonical content."""


class BootstrapAction(StrEnum):
    CREATED = "CREATED"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True)
class BootstrapConfig:
    """Validated runtime input; the database DSN is never represented in logs."""

    policy_version: str
    database_dsn: str = field(repr=False)


@dataclass(frozen=True)
class PolicyRecord:
    owner_tenant_id: Any
    policy_code: str
    policy_type: str
    version: str
    status: str
    source_version_id: Any
    policy_payload: Any
    effective_from: Any
    effective_to: Any
    approved_by_actor_id: Any


class _Cursor(Protocol):
    def __enter__(self) -> _Cursor: ...

    def __exit__(self, *args: object) -> None: ...

    def execute(self, query: str, params: object = None) -> Any: ...

    def fetchall(self) -> list[Mapping[str, Any]]: ...


class _Connection(Protocol):
    def __enter__(self) -> _Connection: ...

    def __exit__(self, *args: object) -> None: ...

    def cursor(self, *, row_factory: Any) -> _Cursor: ...


def desired_policy_payload() -> dict[str, object]:
    """Return a fresh, machine-verifiable payload with no human-approval claim."""
    return {
        "governance_status": GOVERNANCE_STATUS,
        "production_approved": PRODUCTION_APPROVED,
        "purpose_specific": True,
        "supported_purposes": list(SUPPORTED_PURPOSES),
        "synthetic_only": SYNTHETIC_ONLY,
    }


def _payload_sha256(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _database_dsn(value: str) -> str:
    """Convert a SQLAlchemy PostgreSQL URL into a libpq-compatible DSN.

    The URL remains in memory only. Error messages intentionally identify only
    the invalid field and never include its value.
    """
    stripped = value.strip()
    for scheme in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if stripped.startswith(scheme):
            return "postgresql://" + stripped.removeprefix(scheme)
    if stripped.startswith("postgresql://"):
        return stripped
    raise BootstrapConfigurationError("DATABASE_URL must be PostgreSQL")


def load_config(environ: Mapping[str, str] | None = None) -> BootstrapConfig:
    """Load the strict staging-only bootstrap contract from the environment."""
    source = os.environ if environ is None else environ
    if source.get("APP_ENV", "").strip().lower() != "staging":
        raise BootstrapConfigurationError("APP_ENV must be staging")

    policy_version = source.get(CONSENT_POLICY_VERSION_ENV, "").strip()
    if not _POLICY_VERSION_PATTERN.fullmatch(policy_version):
        raise BootstrapConfigurationError(f"{CONSENT_POLICY_VERSION_ENV} is invalid")

    database_url = source.get("DATABASE_URL", "")
    if not database_url.strip():
        raise BootstrapConfigurationError("DATABASE_URL is required")
    return BootstrapConfig(
        policy_version=policy_version,
        database_dsn=_database_dsn(database_url),
    )


def _record_from_row(row: Mapping[str, Any]) -> PolicyRecord:
    return PolicyRecord(
        owner_tenant_id=row["owner_tenant_id"],
        policy_code=row["policy_code"],
        policy_type=row["policy_type"],
        version=row["version"],
        status=row["status"],
        source_version_id=row["source_version_id"],
        policy_payload=row["policy_payload"],
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
        approved_by_actor_id=row["approved_by_actor_id"],
    )


def _is_expected(record: PolicyRecord, policy_version: str) -> bool:
    return record == PolicyRecord(
        owner_tenant_id=None,
        policy_code=POLICY_CODE,
        policy_type=POLICY_TYPE,
        version=policy_version,
        status=POLICY_STATUS,
        source_version_id=None,
        policy_payload=desired_policy_payload(),
        effective_from=None,
        effective_to=None,
        approved_by_actor_id=None,
    )


def reconcile_consent_policy(
    config: BootstrapConfig,
    *,
    connect: Callable[..., _Connection] = psycopg.connect,
) -> BootstrapAction:
    """Create the exact staging policy or prove that it already matches.

    A transaction-scoped advisory lock serializes this command. All consent
    policies using the requested version are inspected, including tenant-owned
    rows, because allowing an ambiguous same-version policy would make policy
    resolution order-dependent.
    """
    with connect(config.database_dsn) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_BOOTSTRAP_LOCK_ID,))
            # Also serialize with ordinary INSERT/UPDATE writers. Without this lock,
            # a non-cooperating writer could create an ambiguous same-version row
            # between our absence check and transaction commit.
            cursor.execute("LOCK TABLE eldercare_ai.policy_registry IN SHARE ROW EXCLUSIVE MODE")
            cursor.execute(
                """
                SELECT owner_tenant_id, policy_code, policy_type, version, status,
                       source_version_id, policy_payload, effective_from, effective_to,
                       approved_by_actor_id
                  FROM eldercare_ai.policy_registry
                 WHERE policy_type = %s AND version = %s
                 FOR UPDATE
                """,
                (POLICY_TYPE, config.policy_version),
            )
            existing = [_record_from_row(row) for row in cursor.fetchall()]
            if existing:
                if len(existing) != 1 or not _is_expected(existing[0], config.policy_version):
                    raise ExistingPolicyMismatchError(
                        "requested consent policy version already has different content"
                    )
                return BootstrapAction.UNCHANGED

            cursor.execute(
                """
                INSERT INTO eldercare_ai.policy_registry (
                    owner_tenant_id, policy_code, policy_type, version, status,
                    source_version_id, policy_payload, effective_from, effective_to,
                    approved_by_actor_id
                ) VALUES (
                    NULL, %s, %s, %s, %s,
                    NULL, %s::jsonb, NULL, NULL,
                    NULL
                )
                """,
                (
                    POLICY_CODE,
                    POLICY_TYPE,
                    config.policy_version,
                    POLICY_STATUS,
                    json.dumps(desired_policy_payload(), separators=(",", ":"), sort_keys=True),
                ),
            )
            return BootstrapAction.CREATED


def build_receipt(config: BootstrapConfig, action: BootstrapAction) -> dict[str, object]:
    """Build a non-sensitive stdout receipt suitable for CloudWatch retention."""
    return {
        "schema_version": "1.0",
        "command": "consent-policy-bootstrap",
        "status": "SUCCESS",
        "action": action.value,
        "completed_at": datetime.now(UTC).isoformat(),
        "app_env": "staging",
        "synthetic_only": SYNTHETIC_ONLY,
        "governance_status": GOVERNANCE_STATUS,
        "production_approved": PRODUCTION_APPROVED,
        "policy_code": POLICY_CODE,
        "policy_type": POLICY_TYPE,
        "policy_version": config.policy_version,
        "policy_payload_sha256": _payload_sha256(desired_policy_payload()),
    }


def _failure_receipt(reason_code: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "command": "consent-policy-bootstrap",
        "status": "FAILED",
        "reason_code": reason_code,
        "completed_at": datetime.now(UTC).isoformat(),
        "synthetic_only": SYNTHETIC_ONLY,
        "governance_status": GOVERNANCE_STATUS,
        "production_approved": PRODUCTION_APPROVED,
    }


def main(argv: Sequence[str] | None = None) -> None:
    """Run once and emit exactly one secret-independent JSON record."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print(json.dumps(_failure_receipt("ARGUMENTS_NOT_ALLOWED"), sort_keys=True))
        raise SystemExit(64)

    try:
        config = load_config()
        action = reconcile_consent_policy(config)
    except BootstrapConfigurationError as exc:
        print(json.dumps(_failure_receipt("CONFIGURATION_INVALID"), sort_keys=True))
        raise SystemExit(64) from exc
    except ExistingPolicyMismatchError as exc:
        print(json.dumps(_failure_receipt("EXISTING_VERSION_MISMATCH"), sort_keys=True))
        raise SystemExit(1) from exc
    except Exception as exc:
        # Driver exceptions can contain hostnames or credentials. Never print them.
        print(json.dumps(_failure_receipt("DATABASE_OPERATION_FAILED"), sort_keys=True))
        raise SystemExit(1) from exc

    print(json.dumps(build_receipt(config, action), sort_keys=True))


if __name__ == "__main__":
    main()
