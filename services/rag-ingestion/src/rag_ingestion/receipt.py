"""Vector-free ingestion receipt creation and atomic persistence."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rag_ingestion.allowlist import Allowlist


@dataclass(frozen=True, slots=True)
class GovernanceReceipt:
    governance_status: str
    production_approved: bool
    allowlist_status: str
    project_owner_risk_acceptance: str
    human_source_review: str
    production_status: str


@dataclass(slots=True)
class IngestionReceipt:
    schema_version: str
    run_id: str
    mode: str
    status: str
    started_at: str
    completed_at: str | None
    allowlist_path: str
    allowlist_sha256: str
    chunks_dir: str
    source_count: int
    allowlist_chunk_count: int
    validated_chunk_count: int
    embedding_model_id: str
    embedding_dimension: int
    embedding_success_count: int
    embedding_failure_count: int
    index_name: str
    index_alias: str
    indexed_document_count: int
    duplicate_id_count: int
    governance: GovernanceReceipt
    errors: list[str] = field(default_factory=list)

    def mark_verified_pending_alias(self) -> None:
        self.status = "VERIFIED_PENDING_ALIAS"
        self.completed_at = None

    def complete(self, status: str) -> None:
        self.status = status
        self.completed_at = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        _assert_vector_free(result)
        return result


def new_receipt(
    *,
    allowlist: Allowlist,
    chunks_dir: Path,
    model_id: str,
    dimension: int,
    index_name: str,
    index_alias: str,
    mode: str,
    expected_allowlist_sha256: str | None,
    require_owner_signature: bool,
    production_enabled: bool,
    repository_root: Path | None = None,
) -> IngestionReceipt:
    if mode != "staging" or production_enabled:
        raise ValueError("this receipt contract only supports staging ingestion")
    decision = allowlist.assert_effective_for_execution(
        expected_allowlist_sha256,
        mode=mode,
        require_owner_signature=require_owner_signature,
        production_enabled=production_enabled,
    )
    governance = allowlist.governance
    return IngestionReceipt(
        schema_version="1.0.0",
        run_id=str(uuid.uuid4()),
        mode=mode,
        status="VALIDATED",
        started_at=_utc_now(),
        completed_at=None,
        allowlist_path=_display_path(allowlist.path, repository_root),
        allowlist_sha256=allowlist.sha256,
        chunks_dir=_display_path(chunks_dir, repository_root),
        source_count=allowlist.declared_source_count,
        allowlist_chunk_count=allowlist.declared_chunk_count,
        validated_chunk_count=0,
        embedding_model_id=model_id,
        embedding_dimension=dimension,
        embedding_success_count=0,
        embedding_failure_count=0,
        index_name=index_name,
        index_alias=index_alias,
        indexed_document_count=0,
        duplicate_id_count=0,
        governance=GovernanceReceipt(
            governance_status=decision.governance_status,
            production_approved=decision.production_approved,
            allowlist_status=governance.allowlist_status,
            project_owner_risk_acceptance=governance.project_owner_risk_acceptance,
            human_source_review=governance.human_source_review,
            production_status=governance.production_status,
        ),
    )


def write_receipt(receipt: IngestionReceipt, path: Path) -> None:
    payload = receipt.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _assert_vector_free(value: Any, path: str = "receipt") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in {"embedding", "embeddings", "vector", "vectors", "text"}:
                raise ValueError(f"{path} must not contain vector or source text fields")
            _assert_vector_free(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_vector_free(child, f"{path}[{index}]")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _display_path(path: Path, repository_root: Path | None) -> str:
    resolved = path.expanduser().resolve()
    if repository_root is None:
        return str(resolved)
    try:
        return resolved.relative_to(repository_root.expanduser().resolve()).as_posix()
    except ValueError:
        return str(resolved)
