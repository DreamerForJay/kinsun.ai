from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from conftest import write_dataset

from rag_ingestion.allowlist import load_allowlist
from rag_ingestion.bulk_ingester import BulkIngester, BulkIngestionError, build_index_document
from rag_ingestion.chunk_loader import load_allowlisted_chunks
from rag_ingestion.opensearch_client import IndexedDocument
from rag_ingestion.validator import ValidatedChunk, validate_chunks

DIMENSION = 1024


class FakeBulkClient:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.duplicates: tuple[str, ...] = ()
        self.deleted: list[str] = []
        self.aliases: list[tuple[str, str]] = []
        self.reported_count: int | None = None
        self.deferred_counts: list[int] = []
        self.count_calls = 0
        self.bulk_called = False

    def bulk_create(self, index_name: str, documents: Sequence[tuple[str, dict[str, Any]]]) -> int:
        self.bulk_called = True
        self.documents = dict(documents)
        return len(documents)

    def count_documents(self, index_name: str) -> int:
        self.count_calls += 1
        if self.deferred_counts:
            return self.deferred_counts.pop(0)
        return len(self.documents) if self.reported_count is None else self.reported_count

    def duplicate_chunk_ids(self, index_name: str) -> tuple[str, ...]:
        return self.duplicates

    def fetch_documents(
        self, index_name: str, document_ids: Sequence[str], *, batch_size: int = 200
    ) -> tuple[IndexedDocument, ...]:
        return tuple(IndexedDocument(item, self.documents[item]) for item in document_ids)

    def delete_index(self, index_name: str) -> None:
        self.deleted.append(index_name)
        self.documents.clear()

    def set_alias(self, index_name: str, alias_name: str) -> None:
        self.aliases.append((index_name, alias_name))


def _validated_chunk(tmp_path: Path) -> ValidatedChunk:
    manifest_path, chunks_dir = write_dataset(tmp_path)
    allowlist = load_allowlist(manifest_path)
    return validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist).chunks[0]


def _vector() -> tuple[float, ...]:
    return tuple(0.01 for _ in range(DIMENSION))


def test_bulk_ingest_uses_chunk_id_as_id_and_verifies_count(tmp_path: Path) -> None:
    chunk = _validated_chunk(tmp_path)
    client = FakeBulkClient()

    report = BulkIngester(client, dimension=DIMENSION).ingest(
        index_name="synthetic-staging-v1",
        alias_name="synthetic-staging",
        chunks=[chunk],
        vectors={chunk.chunk_id: _vector()},
    )

    assert list(client.documents) == [chunk.chunk_id]
    assert client.documents[chunk.chunk_id]["chunk_id"] == chunk.chunk_id
    assert report.indexed_document_count == 1
    assert report.duplicate_id_count == 0
    assert client.aliases == [("synthetic-staging-v1", "synthetic-staging")]


def test_wrong_vector_dimension_fails_before_bulk(tmp_path: Path) -> None:
    chunk = _validated_chunk(tmp_path)
    client = FakeBulkClient()

    with pytest.raises(BulkIngestionError, match="exactly 1024"):
        BulkIngester(client, dimension=DIMENSION).ingest(
            index_name="synthetic-staging-v1",
            alias_name="synthetic-staging",
            chunks=[chunk],
            vectors={chunk.chunk_id: tuple(0.0 for _ in range(DIMENSION - 1))},
        )

    assert client.bulk_called is False


def test_verify_waits_for_serverless_document_visibility(tmp_path: Path) -> None:
    chunk = _validated_chunk(tmp_path)
    client = FakeBulkClient()
    client.deferred_counts = [0, 0]
    sleeps: list[float] = []

    report = BulkIngester(client, dimension=DIMENSION, sleeper=sleeps.append).ingest(
        index_name="synthetic-staging-v1",
        alias_name="synthetic-staging",
        chunks=[chunk],
        vectors={chunk.chunk_id: _vector()},
    )

    assert report.indexed_document_count == 1
    assert client.count_calls == 3
    assert sleeps == [5.0, 5.0]
    assert client.deleted == []


def test_post_ingest_count_mismatch_rolls_back_staging_index(tmp_path: Path) -> None:
    chunk = _validated_chunk(tmp_path)
    client = FakeBulkClient()
    client.reported_count = 0
    sleeps: list[float] = []

    with pytest.raises(BulkIngestionError, match="document count"):
        BulkIngester(
            client,
            dimension=DIMENSION,
            sleeper=sleeps.append,
            visibility_attempts=3,
        ).ingest(
            index_name="synthetic-staging-v1",
            alias_name="synthetic-staging",
            chunks=[chunk],
            vectors={chunk.chunk_id: _vector()},
        )

    assert client.count_calls == 3
    assert len(sleeps) == 2
    assert client.deleted == ["synthetic-staging-v1"]
    assert client.aliases == []


def test_count_above_expected_rolls_back_without_waiting(tmp_path: Path) -> None:
    chunk = _validated_chunk(tmp_path)
    client = FakeBulkClient()
    client.reported_count = 2
    sleeps: list[float] = []

    with pytest.raises(BulkIngestionError, match="document count"):
        BulkIngester(client, dimension=DIMENSION, sleeper=sleeps.append).ingest(
            index_name="synthetic-staging-v1",
            alias_name="synthetic-staging",
            chunks=[chunk],
            vectors={chunk.chunk_id: _vector()},
        )

    assert sleeps == []
    assert client.deleted == ["synthetic-staging-v1"]


def test_post_ingest_duplicate_chunk_id_rolls_back(tmp_path: Path) -> None:
    chunk = _validated_chunk(tmp_path)
    client = FakeBulkClient()
    client.duplicates = (chunk.chunk_id,)

    with pytest.raises(BulkIngestionError, match="duplicate"):
        BulkIngester(client, dimension=DIMENSION).ingest(
            index_name="synthetic-staging-v1",
            alias_name="synthetic-staging",
            chunks=[chunk],
            vectors={chunk.chunk_id: _vector()},
        )

    assert client.deleted == ["synthetic-staging-v1"]


def test_high_risk_filter_fields_are_normalized_at_top_level(tmp_path: Path) -> None:
    chunk = _validated_chunk(tmp_path)
    changed = dict(chunk.loaded.data)
    metadata = dict(changed["metadata"])
    metadata["stop_normal_rag"] = True
    metadata["current_status"] = "current"
    changed["metadata"] = metadata
    modified = ValidatedChunk(
        loaded=type(chunk.loaded)(changed, chunk.loaded.file_path, chunk.loaded.line_number),
        allowlist_entry=chunk.allowlist_entry,
        text_sha256=chunk.text_sha256,
        embedding_text_sha256=chunk.embedding_text_sha256,
    )

    document = build_index_document(modified, _vector())

    assert document["stop_normal_rag"] is True
    assert document["current_status"] == "current"
    assert document["document_name"] == "Synthetic Care Guide"
    assert document["source_url"] == "https://example.invalid/synthetic-guide"


def test_official_page_url_is_accepted_when_no_direct_file_link_exists(tmp_path: Path) -> None:
    """Some agencies publish only a listing page, with no stable file link."""

    chunk = _validated_chunk(tmp_path)
    changed = dict(chunk.loaded.data)
    metadata = dict(changed["metadata"])
    metadata.pop("official_source_url")
    metadata["official_source_page_url"] = "https://example.invalid/agency/list?nodeid=170"
    changed["metadata"] = metadata
    modified = ValidatedChunk(
        loaded=type(chunk.loaded)(changed, chunk.loaded.file_path, chunk.loaded.line_number),
        allowlist_entry=chunk.allowlist_entry,
        text_sha256=chunk.text_sha256,
        embedding_text_sha256=chunk.embedding_text_sha256,
    )

    document = build_index_document(modified, _vector())

    assert document["source_url"] == "https://example.invalid/agency/list?nodeid=170"


def test_direct_file_link_still_wins_over_the_page_url(tmp_path: Path) -> None:
    chunk = _validated_chunk(tmp_path)
    changed = dict(chunk.loaded.data)
    metadata = dict(changed["metadata"])
    metadata["official_source_page_url"] = "https://example.invalid/agency/list?nodeid=170"
    changed["metadata"] = metadata
    modified = ValidatedChunk(
        loaded=type(chunk.loaded)(changed, chunk.loaded.file_path, chunk.loaded.line_number),
        allowlist_entry=chunk.allowlist_entry,
        text_sha256=chunk.text_sha256,
        embedding_text_sha256=chunk.embedding_text_sha256,
    )

    document = build_index_document(modified, _vector())

    assert document["source_url"] == "https://example.invalid/synthetic-guide"


def test_missing_stop_normal_rag_defaults_to_blocked(tmp_path: Path) -> None:
    chunk = _validated_chunk(tmp_path)
    changed = dict(chunk.loaded.data)
    metadata = dict(changed["metadata"])
    metadata.pop("stop_normal_rag")
    changed["metadata"] = metadata
    modified = ValidatedChunk(
        loaded=type(chunk.loaded)(changed, chunk.loaded.file_path, chunk.loaded.line_number),
        allowlist_entry=chunk.allowlist_entry,
        text_sha256=chunk.text_sha256,
        embedding_text_sha256=chunk.embedding_text_sha256,
    )

    assert build_index_document(modified, _vector())["stop_normal_rag"] is True
