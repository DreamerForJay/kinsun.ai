"""Allowlist parsing and governance gates."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CHUNK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,255}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EFFECTIVE_STATUSES = {
    "ACTIVE",
    "APPROVED_FOR_STAGING",
    "EFFECTIVE",
    "SIGNED_AND_EFFECTIVE",
}
SIGNED_ACCEPTANCE_VALUES = {"ACCEPTED", "APPROVED", "SIGNED"}
UNSIGNED_ACCEPTANCE_VALUE = "NOT_SIGNED"
UNSIGNED_DEVELOPMENT_STATUSES = {
    "DRAFT_FIXED_HASH_NOT_EFFECTIVE_UNTIL_PROJECT_OWNER_SIGNATURE",
}
PRODUCTION_APPROVAL_VALUES = {"APPROVED", "ENABLED", "AUTHORIZED"}

UNSIGNED_DEVELOPMENT_OVERRIDE = "UNSIGNED_DEVELOPMENT_OVERRIDE"
SIGNED_ALLOWLIST = "SIGNED_ALLOWLIST"
PRODUCTION_APPROVED = "PRODUCTION_APPROVED"
PRODUCTION_NOT_APPROVED = "PRODUCTION_NOT_APPROVED"
GOVERNANCE_BLOCKED = "BLOCKED"


class AllowlistError(ValueError):
    """Raised when the allowlist is malformed or internally inconsistent."""


class AllowlistGovernanceError(AllowlistError):
    """Raised before any external write when governance is not effective."""

    def __init__(self, message: str, *, decision: ExecutionGovernance | None = None) -> None:
        super().__init__(message)
        self.decision = decision
        self.governance_status = (
            decision.governance_status if decision is not None else GOVERNANCE_BLOCKED
        )
        self.production_approved = decision.production_approved if decision is not None else False


@dataclass(frozen=True, slots=True)
class AllowlistEntry:
    chunk_id: str
    chunk_index: int
    text_sha256: str
    embedding_text_sha256: str
    source_number: int | None
    source_id: str | None
    source_title: str | None
    source_version: str | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GovernanceState:
    allowlist_status: str
    project_owner_risk_acceptance: str
    human_source_review: str
    production_status: str
    effective: bool
    blocking_reasons: tuple[str, ...]

    def to_receipt_dict(self) -> dict[str, str]:
        return {
            "allowlist_status": self.allowlist_status,
            "project_owner_risk_acceptance": self.project_owner_risk_acceptance,
            "human_source_review": self.human_source_review,
            "production_status": self.production_status,
        }


@dataclass(frozen=True, slots=True)
class ExecutionGovernance:
    """Environment-aware decision made before an external SDK is initialized."""

    governance_status: str
    production_approved: bool
    blocking_reasons: tuple[str, ...]

    @property
    def execution_allowed(self) -> bool:
        return not self.blocking_reasons


@dataclass(frozen=True, slots=True)
class Allowlist:
    path: Path
    sha256: str
    schema_version: str
    declared_source_count: int
    declared_chunk_count: int
    entries: tuple[AllowlistEntry, ...]
    governance: GovernanceState
    raw: dict[str, Any]

    @property
    def entry_by_chunk_id(self) -> dict[str, AllowlistEntry]:
        return {entry.chunk_id: entry for entry in self.entries}

    @property
    def allowed_chunk_ids(self) -> tuple[str, ...]:
        return tuple(entry.chunk_id for entry in self.entries)

    def execution_governance(
        self,
        expected_sha256: str | None,
        *,
        mode: str = "staging",
        require_owner_signature: bool = True,
        production_enabled: bool = False,
    ) -> ExecutionGovernance:
        """Evaluate the external hash attestation and environment governance policy.

        The unsigned override is intentionally narrow: it applies only to staging,
        only when the operator explicitly disables the signature requirement, and
        only when the manifest is unsigned (not rejected/revoked) with either an
        effective status or the designated owner-signature-pending status.
        """

        normalized_mode = mode.strip().casefold()
        reasons: list[str] = []
        if expected_sha256 is None or not expected_sha256.strip():
            reasons.append("external allowlist SHA-256 attestation is missing")
        elif not SHA256_PATTERN.fullmatch(expected_sha256.strip()):
            reasons.append("external allowlist SHA-256 attestation is invalid")
        elif not hmac.compare_digest(self.sha256, expected_sha256.strip()):
            reasons.append("external allowlist SHA-256 attestation does not match")

        status = self.governance.allowlist_status.upper()
        acceptance = self.governance.project_owner_risk_acceptance.upper()
        production_status = self.governance.production_status.upper()
        status_is_effective = status in EFFECTIVE_STATUSES
        owner_is_signed = acceptance in SIGNED_ACCEPTANCE_VALUES
        production_context = normalized_mode == "production" or production_enabled

        if normalized_mode not in {"staging", "production"}:
            reasons.append("RAG mode must be staging or production")
            return ExecutionGovernance(
                governance_status=GOVERNANCE_BLOCKED,
                production_approved=False,
                blocking_reasons=tuple(reasons),
            )

        if production_context:
            if normalized_mode != "production":
                reasons.append("RAG_PRODUCTION_ENABLED requires RAG_MODE=production")
            if not production_enabled:
                reasons.append("production execution is disabled")
            if not status_is_effective:
                reasons.append("allowlist status is not effective for production")
            if not owner_is_signed:
                reasons.append("project owner risk acceptance is not signed for production")
            if production_status not in PRODUCTION_APPROVAL_VALUES:
                reasons.append("allowlist production status is not approved")
            production_approved = not reasons
            return ExecutionGovernance(
                governance_status=(
                    PRODUCTION_APPROVED if production_approved else PRODUCTION_NOT_APPROVED
                ),
                production_approved=production_approved,
                blocking_reasons=tuple(reasons),
            )

        override_eligible = (
            not require_owner_signature
            and acceptance == UNSIGNED_ACCEPTANCE_VALUE
            and (status_is_effective or status in UNSIGNED_DEVELOPMENT_STATUSES)
        )
        if require_owner_signature:
            if not status_is_effective:
                reasons.append("allowlist status is not an explicitly effective staging status")
            if not owner_is_signed:
                reasons.append("project owner risk acceptance is not signed")
        elif not override_eligible:
            if not status_is_effective:
                reasons.append("allowlist status is not eligible for unsigned staging execution")
            if not owner_is_signed and acceptance != UNSIGNED_ACCEPTANCE_VALUE:
                reasons.append("project owner acceptance is neither signed nor NOT_SIGNED")

        if override_eligible:
            governance_status = UNSIGNED_DEVELOPMENT_OVERRIDE
        elif status_is_effective and owner_is_signed:
            governance_status = SIGNED_ALLOWLIST
        else:
            governance_status = GOVERNANCE_BLOCKED
        return ExecutionGovernance(
            governance_status=governance_status,
            production_approved=False,
            blocking_reasons=tuple(reasons),
        )

    def execution_blocking_reasons(
        self,
        expected_sha256: str | None,
        *,
        mode: str = "staging",
        require_owner_signature: bool = True,
        production_enabled: bool = False,
    ) -> tuple[str, ...]:
        return self.execution_governance(
            expected_sha256,
            mode=mode,
            require_owner_signature=require_owner_signature,
            production_enabled=production_enabled,
        ).blocking_reasons

    def is_effective_for_execution(
        self,
        expected_sha256: str | None,
        *,
        mode: str = "staging",
        require_owner_signature: bool = True,
        production_enabled: bool = False,
    ) -> bool:
        return self.execution_governance(
            expected_sha256,
            mode=mode,
            require_owner_signature=require_owner_signature,
            production_enabled=production_enabled,
        ).execution_allowed

    def assert_effective_for_execution(
        self,
        expected_sha256: str | None,
        *,
        mode: str = "staging",
        require_owner_signature: bool = True,
        production_enabled: bool = False,
    ) -> ExecutionGovernance:
        decision = self.execution_governance(
            expected_sha256,
            mode=mode,
            require_owner_signature=require_owner_signature,
            production_enabled=production_enabled,
        )
        if not decision.execution_allowed:
            raise AllowlistGovernanceError(
                "allowlist is not attested for external execution: "
                + "; ".join(decision.blocking_reasons),
                decision=decision,
            )
        return decision


def load_allowlist(path: Path) -> Allowlist:
    resolved = path.expanduser().resolve()
    try:
        payload = resolved.read_bytes()
    except OSError as exc:
        raise AllowlistError(f"cannot read allowlist: {type(exc).__name__}") from exc
    try:
        raw = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AllowlistError(f"allowlist is not valid UTF-8 JSON: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise AllowlistError("allowlist root must be an object")

    schema_version = _required_string(raw, "schema_version")
    declared_source_count = _required_nonnegative_int(raw, "source_count")
    declared_chunk_count = _required_nonnegative_int(raw, "chunk_count")
    entries_raw = raw.get("entries")
    sources_raw = raw.get("sources")
    if not isinstance(entries_raw, list) or not entries_raw:
        raise AllowlistError("allowlist entries must be a non-empty array")
    if not isinstance(sources_raw, list):
        raise AllowlistError("allowlist sources must be an array")
    if len(sources_raw) != declared_source_count:
        raise AllowlistError("allowlist source_count does not match sources")
    if len(entries_raw) != declared_chunk_count:
        raise AllowlistError("allowlist chunk_count does not match entries")

    source_numbers: set[int] = set()
    source_ids_by_number: dict[int, str] = {}
    for index, source in enumerate(sources_raw):
        if not isinstance(source, dict):
            raise AllowlistError(f"allowlist source {index} must be an object")
        source_number = source.get("source_number")
        expected_count = source.get("chunk_count")
        if (
            isinstance(source_number, bool)
            or not isinstance(source_number, int)
            or isinstance(expected_count, bool)
            or not isinstance(expected_count, int)
        ):
            raise AllowlistError(f"allowlist source {index} has invalid counts")
        if source_number in source_numbers:
            raise AllowlistError(f"duplicate allowlist source_number: {source_number}")
        source_numbers.add(source_number)
        source_ids_by_number[source_number] = _required_string(source, "source_id")

    entries: list[AllowlistEntry] = []
    seen: set[str] = set()
    per_source: dict[int, int] = {}
    for index, item in enumerate(entries_raw):
        if not isinstance(item, dict):
            raise AllowlistError(f"allowlist entry {index} must be an object")
        chunk_id = _required_string(item, "chunk_id")
        if not CHUNK_ID_PATTERN.fullmatch(chunk_id):
            raise AllowlistError(f"allowlist entry {index} has invalid chunk_id")
        if chunk_id in seen:
            raise AllowlistError(f"duplicate allowlist chunk_id: {chunk_id}")
        seen.add(chunk_id)
        text_sha256 = _required_hash(item, "text_sha256", index)
        embedding_text_sha256 = _required_hash(item, "embedding_text_sha256", index)
        chunk_index = _required_nonnegative_int(item, "chunk_index")
        source_number = item.get("source_number")
        if source_number is not None and (
            isinstance(source_number, bool) or not isinstance(source_number, int)
        ):
            raise AllowlistError(f"allowlist entry {index} has invalid source_number")
        if source_number not in source_ids_by_number:
            raise AllowlistError(f"allowlist entry {index} references an unknown source_number")
        per_source[source_number] = per_source.get(source_number, 0) + 1
        explicit_source_id = _optional_string(item, "source_id")
        normalized_source_id = explicit_source_id or source_ids_by_number[source_number]
        if (
            explicit_source_id is not None
            and explicit_source_id != source_ids_by_number[source_number]
        ):
            raise AllowlistError(f"allowlist entry {index} source_id does not match source_number")
        entries.append(
            AllowlistEntry(
                chunk_id=chunk_id,
                chunk_index=chunk_index,
                text_sha256=text_sha256,
                embedding_text_sha256=embedding_text_sha256,
                source_number=source_number,
                source_id=normalized_source_id,
                source_title=_optional_string(item, "source_title"),
                source_version=_optional_string(item, "source_version"),
                raw=dict(item),
            )
        )

    for index, source in enumerate(sources_raw):
        source_number = source["source_number"]
        expected_count = source["chunk_count"]
        if per_source.get(source_number, 0) != expected_count:
            raise AllowlistError(f"source {source_number} chunk_count does not match entries")

    governance = _governance_state(raw)
    return Allowlist(
        path=resolved,
        sha256=hashlib.sha256(payload).hexdigest(),
        schema_version=schema_version,
        declared_source_count=declared_source_count,
        declared_chunk_count=declared_chunk_count,
        entries=tuple(entries),
        governance=governance,
        raw=raw,
    )


def _governance_state(raw: dict[str, Any]) -> GovernanceState:
    status = str(raw.get("status", "MISSING"))
    acceptance = str(raw.get("project_owner_risk_acceptance", "MISSING"))
    human_review = str(raw.get("human_source_review", "MISSING"))
    production_status = str(raw.get("production_status", "MISSING"))
    reasons: list[str] = []
    if status.upper() not in EFFECTIVE_STATUSES:
        reasons.append("allowlist status is not an explicitly effective staging status")
    if acceptance.upper() not in SIGNED_ACCEPTANCE_VALUES:
        reasons.append("project owner risk acceptance is not signed")
    return GovernanceState(
        allowlist_status=status,
        project_owner_risk_acceptance=acceptance,
        human_source_review=human_review,
        production_status=production_status,
        effective=not reasons,
        blocking_reasons=tuple(reasons),
    )


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AllowlistError(f"allowlist {key} must be a non-empty string")
    return value


def _optional_string(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AllowlistError(f"allowlist {key} must be a non-empty string when present")
    return value


def _required_nonnegative_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AllowlistError(f"allowlist {key} must be a non-negative integer")
    return value


def _required_hash(item: dict[str, Any], key: str, index: int) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise AllowlistError(f"allowlist entry {index} has invalid {key}")
    return value
