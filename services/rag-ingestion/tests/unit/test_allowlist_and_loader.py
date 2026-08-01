from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import synthetic_chunk, write_dataset

from rag_ingestion.allowlist import (
    UNSIGNED_DEVELOPMENT_OVERRIDE,
    AllowlistError,
    AllowlistGovernanceError,
    load_allowlist,
)
from rag_ingestion.chunk_loader import ChunkLoadError, load_allowlisted_chunks


def test_allowlist_normalizes_missing_entry_source_id(tmp_path: Path) -> None:
    manifest_path, _ = write_dataset(tmp_path, omit_entry_source_id=True)

    allowlist = load_allowlist(manifest_path)

    assert allowlist.entries[0].source_id == "synthetic_source"


def test_governance_is_exposed_and_external_execution_fails_closed(tmp_path: Path) -> None:
    manifest_path, _ = write_dataset(tmp_path, effective=False)
    allowlist = load_allowlist(manifest_path)

    assert allowlist.governance.effective is False
    assert allowlist.governance.human_source_review == "NOT_COMPLETED"
    with pytest.raises(AllowlistGovernanceError):
        allowlist.assert_effective_for_execution(None)


@pytest.mark.parametrize(
    "expected_sha256",
    [None, "not-a-sha256", "0" * 64],
)
def test_external_hash_attestation_is_required_and_must_match(
    tmp_path: Path, expected_sha256: str | None
) -> None:
    manifest_path, _ = write_dataset(tmp_path, effective=True)
    allowlist = load_allowlist(manifest_path)

    assert allowlist.is_effective_for_execution(expected_sha256) is False
    with pytest.raises(AllowlistGovernanceError):
        allowlist.assert_effective_for_execution(expected_sha256)


def test_matching_external_hash_attestation_allows_effective_manifest(tmp_path: Path) -> None:
    manifest_path, _ = write_dataset(tmp_path, effective=True)
    allowlist = load_allowlist(manifest_path)

    allowlist.assert_effective_for_execution(allowlist.sha256)

    assert allowlist.is_effective_for_execution(allowlist.sha256) is True


def test_unsigned_staging_override_allows_exactly_attested_development_manifest(
    tmp_path: Path,
) -> None:
    manifest_path, _ = write_dataset(tmp_path, effective=False)
    allowlist = load_allowlist(manifest_path)

    decision = allowlist.assert_effective_for_execution(
        allowlist.sha256,
        mode="staging",
        require_owner_signature=False,
        production_enabled=False,
    )

    assert decision.governance_status == UNSIGNED_DEVELOPMENT_OVERRIDE
    assert decision.production_approved is False
    assert decision.execution_allowed is True


@pytest.mark.parametrize("expected_sha256", [None, "0" * 64])
def test_unsigned_staging_override_never_bypasses_external_hash_attestation(
    tmp_path: Path, expected_sha256: str | None
) -> None:
    manifest_path, _ = write_dataset(tmp_path, effective=False)
    allowlist = load_allowlist(manifest_path)

    with pytest.raises(AllowlistGovernanceError, match="attestation") as raised:
        allowlist.assert_effective_for_execution(
            expected_sha256,
            mode="staging",
            require_owner_signature=False,
            production_enabled=False,
        )

    assert raised.value.governance_status == UNSIGNED_DEVELOPMENT_OVERRIDE
    assert raised.value.production_approved is False


def test_owner_signature_can_still_be_required_explicitly_in_staging(tmp_path: Path) -> None:
    manifest_path, _ = write_dataset(tmp_path, effective=False)
    allowlist = load_allowlist(manifest_path)

    with pytest.raises(AllowlistGovernanceError, match="not signed"):
        allowlist.assert_effective_for_execution(
            allowlist.sha256,
            mode="staging",
            require_owner_signature=True,
            production_enabled=False,
        )


@pytest.mark.parametrize(
    ("mode", "production_enabled"),
    [("production", False), ("production", True), ("staging", True)],
)
def test_production_context_never_uses_unsigned_override(
    tmp_path: Path, mode: str, production_enabled: bool
) -> None:
    manifest_path, _ = write_dataset(tmp_path, effective=False)
    allowlist = load_allowlist(manifest_path)

    decision = allowlist.execution_governance(
        allowlist.sha256,
        mode=mode,
        require_owner_signature=False,
        production_enabled=production_enabled,
    )

    assert decision.execution_allowed is False
    assert decision.production_approved is False
    assert "PRODUCTION" in decision.governance_status
    assert any("not signed for production" in reason for reason in decision.blocking_reasons)


def test_revoked_manifest_is_not_eligible_for_unsigned_staging_override(tmp_path: Path) -> None:
    manifest_path, _ = write_dataset(tmp_path, effective=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "REVOKED"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    allowlist = load_allowlist(manifest_path)

    with pytest.raises(AllowlistGovernanceError, match="not eligible"):
        allowlist.assert_effective_for_execution(
            allowlist.sha256,
            mode="staging",
            require_owner_signature=False,
            production_enabled=False,
        )


def test_chunk_outside_allowlist_is_rejected(tmp_path: Path) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path)
    outside = synthetic_chunk("synthetic_source_chunk_002")
    with (chunks_dir / "outside.jsonl").open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(outside))
        handle.write("\n")

    with pytest.raises(ChunkLoadError, match="outside allowlist"):
        load_allowlisted_chunks(chunks_dir, load_allowlist(manifest_path))


def test_duplicate_chunk_id_is_rejected(tmp_path: Path) -> None:
    chunk = synthetic_chunk()
    manifest_path, chunks_dir = write_dataset(tmp_path, chunks=[chunk])
    with (chunks_dir / "duplicate.jsonl").open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(chunk))
        handle.write("\n")

    with pytest.raises(ChunkLoadError, match="duplicate chunk_id"):
        load_allowlisted_chunks(chunks_dir, load_allowlist(manifest_path))


@pytest.mark.parametrize("forbidden", ["pending-revalidation", "not-authorized"])
def test_unreviewed_sibling_directories_are_rejected(forbidden: str, tmp_path: Path) -> None:
    """Both tiers sit beside the approved set and hold uncleared chunks.

    The Allowlist would also reject their chunk IDs, but that is the second
    line of defence; pointing the loader at either directory must fail first.
    """

    manifest_path, chunks_dir = write_dataset(tmp_path / forbidden)

    with pytest.raises(ChunkLoadError, match=forbidden):
        load_allowlisted_chunks(chunks_dir, load_allowlist(manifest_path))


def test_invalid_jsonl_is_rejected_without_returning_partial_set(tmp_path: Path) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path)
    (chunks_dir / "invalid.jsonl").write_text("{not json}\n", encoding="utf-8")

    with pytest.raises(ChunkLoadError, match="invalid JSONL"):
        load_allowlisted_chunks(chunks_dir, load_allowlist(manifest_path))


def test_allowlist_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    manifest_path, _ = write_dataset(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entries"].append(dict(manifest["entries"][0]))
    manifest["chunk_count"] = 2
    manifest["sources"][0]["chunk_count"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AllowlistError, match="duplicate allowlist chunk_id"):
        load_allowlist(manifest_path)


@pytest.mark.parametrize("count_field", ["source_count", "chunk_count"])
def test_unsigned_override_cannot_bypass_declared_allowlist_counts(
    tmp_path: Path, count_field: str
) -> None:
    manifest_path, _ = write_dataset(tmp_path, effective=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[count_field] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AllowlistError, match=count_field):
        load_allowlist(manifest_path)
