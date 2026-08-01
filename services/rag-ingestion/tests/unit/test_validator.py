from __future__ import annotations

from pathlib import Path

import pytest
from conftest import synthetic_chunk, write_dataset

from rag_ingestion.allowlist import load_allowlist
from rag_ingestion.chunk_loader import LoadedChunk, load_allowlisted_chunks
from rag_ingestion.validator import ChunkValidationError, validate_chunks


def _load(tmp_path: Path) -> tuple[object, tuple[LoadedChunk, ...]]:
    manifest_path, chunks_dir = write_dataset(tmp_path)
    allowlist = load_allowlist(manifest_path)
    return allowlist, load_allowlisted_chunks(chunks_dir, allowlist)


def test_hash_mismatch_stops_validation(tmp_path: Path) -> None:
    allowlist, loaded = _load(tmp_path)
    changed = dict(loaded[0].data)
    changed["text"] = "tampered synthetic text"
    invalid = LoadedChunk(changed, loaded[0].file_path, loaded[0].line_number)

    with pytest.raises(ChunkValidationError, match="text hash mismatch"):
        validate_chunks((invalid,), allowlist)


def test_missing_embedding_text_is_rejected(tmp_path: Path) -> None:
    allowlist, loaded = _load(tmp_path)
    changed = dict(loaded[0].data)
    changed.pop("embedding_text")
    invalid = LoadedChunk(changed, loaded[0].file_path, loaded[0].line_number)

    with pytest.raises(ChunkValidationError, match="embedding_text missing"):
        validate_chunks((invalid,), allowlist)


def test_duplicate_chunk_id_is_rejected_even_if_loader_is_bypassed(tmp_path: Path) -> None:
    allowlist, loaded = _load(tmp_path)

    with pytest.raises(ChunkValidationError, match="duplicate chunk_id"):
        validate_chunks((loaded[0], loaded[0]), allowlist)


def test_valid_complete_set_returns_counts(tmp_path: Path) -> None:
    chunks = [synthetic_chunk()]
    manifest_path, chunks_dir = write_dataset(tmp_path, chunks=chunks)
    allowlist = load_allowlist(manifest_path)

    result = validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist)

    assert result.source_count == 1
    assert result.chunk_count == 1
    assert result.allowlist_effective is True
