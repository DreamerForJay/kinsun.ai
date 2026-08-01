from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import synthetic_chunk, write_dataset

from rag_ingestion.allowlist import load_allowlist
from rag_ingestion.allowlist_builder import (
    AllowlistBuildError,
    rebuild_allowlist,
    write_allowlist,
)
from rag_ingestion.chunk_loader import load_allowlisted_chunks
from rag_ingestion.validator import validate_chunks


def second_chunk() -> dict[str, Any]:
    chunk = synthetic_chunk("synthetic_source_chunk_002")
    chunk["chunk_index"] = 2
    chunk["text"] = "A second synthetic reference paragraph."
    chunk["embedding_text"] = "A second synthetic reference paragraph for retrieval."
    metadata = dict(chunk["metadata"])
    metadata.pop("text_sha256")
    metadata.pop("embedding_text_sha256")
    chunk["metadata"] = metadata
    return chunk


def test_rebuilt_manifest_is_accepted_by_the_real_validator(tmp_path: Path) -> None:
    """The builder and the validator must never disagree about a hash.

    A single wrong byte rejects the entire ingestion run, so this asserts the
    round trip rather than the hash algorithm in isolation.
    """

    manifest_path, chunks_dir = write_dataset(tmp_path, chunks=[synthetic_chunk(), second_chunk()])
    # Corrupt every stored hash so a passing round trip can only come from the
    # rebuild, not from what write_dataset already computed.
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in document["entries"]:
        entry["text_sha256"] = "0" * 64
        entry["embedding_text_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    rebuild = rebuild_allowlist(manifest_path=manifest_path, chunks_dir=chunks_dir)
    write_allowlist(rebuild, manifest_path)

    allowlist = load_allowlist(manifest_path)
    assert allowlist.sha256 == rebuild.sha256
    result = validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist)
    assert result.chunk_count == 2
    assert result.source_count == 1


def test_rebuild_is_stable_when_nothing_changed(tmp_path: Path) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path)

    first = rebuild_allowlist(manifest_path=manifest_path, chunks_dir=chunks_dir)
    write_allowlist(first, manifest_path)
    second = rebuild_allowlist(manifest_path=manifest_path, chunks_dir=chunks_dir)

    assert second.sha256 == first.sha256
    assert second.changed is False
    assert second.serialized_differs is False
    assert (second.added, second.removed, second.rehashed) == ([], [], [])


def test_reformatting_alone_is_not_reported_as_a_change(tmp_path: Path) -> None:
    """Rewriting for formatting would invalidate the attested SHA for nothing."""

    manifest_path, chunks_dir = write_dataset(tmp_path)

    rebuild = rebuild_allowlist(manifest_path=manifest_path, chunks_dir=chunks_dir)

    # write_dataset emits compact JSON, so the bytes differ from the rebuild.
    assert rebuild.serialized_differs is True
    assert rebuild.changed is False
    assert rebuild.to_summary()["formatting_only_difference"] is True
    assert rebuild.to_summary()["status"] == "UNCHANGED"


def test_edited_chunk_text_is_reported_as_rehashed(tmp_path: Path) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path)
    jsonl = chunks_dir / "synthetic.jsonl"
    chunk = json.loads(jsonl.read_text(encoding="utf-8").strip())
    chunk["text"] = "Edited public-care reference text."
    chunk["metadata"].pop("text_sha256")
    jsonl.write_text(json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8")

    rebuild = rebuild_allowlist(manifest_path=manifest_path, chunks_dir=chunks_dir)

    assert rebuild.rehashed == ["synthetic_source_chunk_001"]
    assert rebuild.added == []
    assert rebuild.changed is True


def test_chunk_from_an_unreviewed_source_is_refused(tmp_path: Path) -> None:
    """source_number ties a source to the review catalogue; never invent one."""

    stranger = synthetic_chunk("unreviewed_source_chunk_001")
    stranger["source_id"] = "some_unreviewed_source"
    manifest_path, chunks_dir = write_dataset(tmp_path, chunks=[synthetic_chunk(), stranger])

    with pytest.raises(AllowlistBuildError, match="some_unreviewed_source"):
        rebuild_allowlist(manifest_path=manifest_path, chunks_dir=chunks_dir)


def test_governance_is_carried_over_and_never_elevated(tmp_path: Path) -> None:
    manifest_path, chunks_dir = write_dataset(
        tmp_path, chunks=[synthetic_chunk(), second_chunk()], effective=False
    )

    rebuild = rebuild_allowlist(manifest_path=manifest_path, chunks_dir=chunks_dir)
    document = json.loads(rebuild.serialized.decode("utf-8"))

    assert document["status"] == "DRAFT_FIXED_HASH_NOT_EFFECTIVE_UNTIL_PROJECT_OWNER_SIGNATURE"
    assert document["project_owner_risk_acceptance"] == "NOT_SIGNED"
    assert document["human_source_review"] == "NOT_COMPLETED"
    assert document["production_status"] == "BLOCKED"
    assert rebuild.governance["status"] == document["status"]

    new_entry = next(
        entry for entry in document["entries"] if entry["chunk_id"] == "synthetic_source_chunk_002"
    )
    assert new_entry["review_status"] == "needs_review"
    assert new_entry["human_source_review"] == "NOT_COMPLETED"
    assert new_entry["production_gate"] == "BLOCKED"
    assert new_entry["signature_required"] is True


def test_removed_chunk_file_drops_the_entry_and_updates_counts(tmp_path: Path) -> None:
    manifest_path, chunks_dir = write_dataset(tmp_path, chunks=[synthetic_chunk(), second_chunk()])
    jsonl = chunks_dir / "synthetic.jsonl"
    kept = jsonl.read_text(encoding="utf-8").splitlines()[0]
    jsonl.write_text(kept + "\n", encoding="utf-8")

    rebuild = rebuild_allowlist(manifest_path=manifest_path, chunks_dir=chunks_dir)
    document = json.loads(rebuild.serialized.decode("utf-8"))

    assert rebuild.removed == ["synthetic_source_chunk_002"]
    assert document["chunk_count"] == 1
    assert document["sources"][0]["chunk_count"] == 1
