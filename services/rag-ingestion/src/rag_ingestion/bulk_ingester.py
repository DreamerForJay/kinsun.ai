"""Build normalized index documents, bulk create, and verify fail closed."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import sleep
from typing import Any, Protocol
from urllib.parse import urlsplit

from rag_ingestion.opensearch_client import IndexedDocument
from rag_ingestion.settings import REQUIRED_EMBEDDING_DIMENSION
from rag_ingestion.validator import ValidatedChunk

# Serverless refuses the wait_for refresh policy, so a bulk create only becomes
# countable at the next refresh. Measured lag is a few seconds; poll at
# 0, 5, ..., 60 seconds.
COUNT_VISIBILITY_ATTEMPTS = 13
COUNT_VISIBILITY_DELAY_SECONDS = 5.0


class BulkIngestionError(RuntimeError):
    """Raised when preflight, bulk create, or post-ingest verification fails."""


class BulkClient(Protocol):
    def bulk_create(
        self, index_name: str, documents: Sequence[tuple[str, dict[str, Any]]]
    ) -> int: ...

    def count_documents(self, index_name: str) -> int: ...

    def duplicate_chunk_ids(self, index_name: str) -> tuple[str, ...]: ...

    def fetch_documents(
        self, index_name: str, document_ids: Sequence[str], *, batch_size: int = 200
    ) -> tuple[IndexedDocument, ...]: ...

    def delete_index(self, index_name: str) -> None: ...

    def set_alias(self, index_name: str, alias_name: str) -> None: ...


@dataclass(frozen=True, slots=True)
class BulkIngestionReport:
    indexed_document_count: int
    duplicate_id_count: int
    vector_dimension: int
    alias_activated: bool


class BulkIngester:
    def __init__(
        self,
        client: BulkClient,
        *,
        dimension: int,
        sleeper: Callable[[float], None] = sleep,
        visibility_attempts: int = COUNT_VISIBILITY_ATTEMPTS,
        visibility_delay_seconds: float = COUNT_VISIBILITY_DELAY_SECONDS,
    ) -> None:
        if dimension != REQUIRED_EMBEDDING_DIMENSION:
            raise ValueError(f"embedding dimension must be {REQUIRED_EMBEDDING_DIMENSION}")
        if visibility_attempts < 1:
            raise ValueError("visibility_attempts must be at least one")
        if visibility_delay_seconds < 0:
            raise ValueError("visibility_delay_seconds must not be negative")
        self._client = client
        self.dimension = dimension
        self._sleeper = sleeper
        self._visibility_attempts = visibility_attempts
        self._visibility_delay_seconds = visibility_delay_seconds

    def ingest(
        self,
        *,
        index_name: str,
        alias_name: str,
        chunks: Sequence[ValidatedChunk],
        vectors: dict[str, tuple[float, ...]],
        activate_alias: bool = True,
    ) -> BulkIngestionReport:
        _require_staging_resource(index_name)
        _require_staging_resource(alias_name)
        documents = self._preflight_documents(chunks, vectors)
        expected_ids = [document_id for document_id, _ in documents]
        try:
            created = self._client.bulk_create(index_name, documents)
            if created != len(documents):
                raise BulkIngestionError("bulk acknowledged count does not match input")
            report = self.verify(
                index_name=index_name,
                expected_ids=expected_ids,
                expected_count=len(documents),
            )
            if activate_alias:
                self._client.set_alias(index_name, alias_name)
            return BulkIngestionReport(
                indexed_document_count=report.indexed_document_count,
                duplicate_id_count=report.duplicate_id_count,
                vector_dimension=report.vector_dimension,
                alias_activated=activate_alias,
            )
        except Exception as exc:
            try:
                self._client.delete_index(index_name)
            except Exception as rollback_exc:
                raise BulkIngestionError(
                    "ingestion failed and staging rollback also failed"
                ) from rollback_exc
            if isinstance(exc, BulkIngestionError):
                raise
            raise BulkIngestionError(f"ingestion failed: {type(exc).__name__}") from exc

    def verify(
        self,
        *,
        index_name: str,
        expected_ids: Sequence[str],
        expected_count: int,
    ) -> BulkIngestionReport:
        if len(expected_ids) != len(set(expected_ids)):
            raise BulkIngestionError("expected chunk_id values contain duplicates")
        actual_count = self._await_document_count(index_name, expected_count)
        duplicate_ids = self._client.duplicate_chunk_ids(index_name)
        if duplicate_ids:
            raise BulkIngestionError("OpenSearch contains duplicate chunk_id values")
        fetched = self._client.fetch_documents(index_name, expected_ids)
        fetched_ids: set[str] = set()
        for document in fetched:
            if document.document_id in fetched_ids:
                raise BulkIngestionError("OpenSearch returned duplicate document _id values")
            fetched_ids.add(document.document_id)
            if document.source.get("chunk_id") != document.document_id:
                raise BulkIngestionError("OpenSearch _id does not match chunk_id")
            _validate_vector(document.source.get("embedding"), self.dimension)
        if fetched_ids != set(expected_ids):
            raise BulkIngestionError("OpenSearch document IDs do not match allowlist")
        return BulkIngestionReport(
            indexed_document_count=actual_count,
            duplicate_id_count=0,
            vector_dimension=self.dimension,
            alias_activated=False,
        )

    def _await_document_count(self, index_name: str, expected_count: int) -> int:
        """Poll until every created document is countable.

        A count above the expected total means the index was not empty, which
        no amount of waiting can fix, so that case stops immediately.
        """

        actual_count = -1
        for attempt in range(self._visibility_attempts):
            actual_count = self._client.count_documents(index_name)
            if actual_count == expected_count:
                return actual_count
            if actual_count > expected_count or attempt == self._visibility_attempts - 1:
                break
            self._sleeper(self._visibility_delay_seconds)
        raise BulkIngestionError(
            f"OpenSearch document count is {actual_count}, expected {expected_count}"
        )

    def _preflight_documents(
        self,
        chunks: Sequence[ValidatedChunk],
        vectors: dict[str, tuple[float, ...]],
    ) -> list[tuple[str, dict[str, Any]]]:
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise BulkIngestionError("duplicate chunk_id values are not allowed")
        if set(chunk_ids) != set(vectors):
            raise BulkIngestionError("embedding artifact IDs do not match validated chunks")
        documents: list[tuple[str, dict[str, Any]]] = []
        for chunk in chunks:
            vector = vectors[chunk.chunk_id]
            _validate_vector(vector, self.dimension)
            documents.append((chunk.chunk_id, build_index_document(chunk, vector)))
        return documents


def build_index_document(chunk: ValidatedChunk, vector: Sequence[float]) -> dict[str, Any]:
    data = chunk.data
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    document_name = (
        chunk.allowlist_entry.source_title
        or _first_string(data, metadata, "document_title", "document_name", "source_title")
        or _first_string(data, metadata, "title")
    )
    if document_name is None:
        raise BulkIngestionError(f"document name is unavailable for {chunk.chunk_id}")
    current_status = _first_string(data, metadata, "current_status") or "unknown"
    stop_normal_rag = _first_bool(data, metadata, "stop_normal_rag", default=True)
    requires_human_review = _first_bool(data, metadata, "requires_human_review", default=True)
    page_start = _first_positive_int(
        data, metadata, "page_start", "printed_page_start", "physical_page_start"
    )
    page_end = _first_positive_int(
        data, metadata, "page_end", "printed_page_end", "physical_page_end"
    )
    # official_source_page_url is the official page hosting the document, used
    # when a source publishes no direct file link. Ordered last so a direct link
    # still wins, but accepted rather than dropping the citation entirely: a
    # source with a real page URL is citable, and refusing it fails the run.
    source_url = _first_string(
        data,
        metadata,
        "official_source_url",
        "source_url",
        "official_source_page_url",
    )
    source_version = (
        _first_string(
            data,
            metadata,
            "source_version",
            "document_version",
            "source_version_date",
            "artifact_version",
        )
        or chunk.allowlist_entry.source_version
    )
    section = _first_string(data, metadata, "section")
    if section is None:
        raise BulkIngestionError(f"section is unavailable for {chunk.chunk_id}")
    # A web page has no pagination, and source_locator carries the position
    # instead. Both or neither: a half-populated range points nowhere.
    if (page_start is None) != (page_end is None):
        raise BulkIngestionError(f"page range is half-populated for {chunk.chunk_id}")
    if page_start is not None and page_end is not None and page_end < page_start:
        raise BulkIngestionError(f"page range is invalid for {chunk.chunk_id}")
    if source_url is None:
        raise BulkIngestionError(f"source URL is unavailable for {chunk.chunk_id}")
    parsed_source_url = urlsplit(source_url)
    if parsed_source_url.scheme not in {"http", "https"} or not parsed_source_url.netloc:
        raise BulkIngestionError(f"source URL is invalid for {chunk.chunk_id}")
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": data["source_id"],
        "document_name": document_name,
        "section": section,
        "page_start": page_start,
        "page_end": page_end,
        "source_url": source_url,
        "source_locator": _first_string(data, metadata, "source_locator"),
        "text": chunk.text,
        "embedding_text": chunk.embedding_text,
        "embedding": list(vector),
        "current_status": current_status,
        "stop_normal_rag": stop_normal_rag,
        "risk_level": _first_string(data, metadata, "risk_level") or "unknown",
        "requires_human_review": requires_human_review,
        "allowed_audiences": _first_string_list(data, metadata, "allowed_audiences"),
        "allowed_purposes": _first_string_list(data, metadata, "allowed_purposes"),
        "source_version": source_version,
        "last_verified_at": _first_string(
            data, metadata, "last_verified_at", "last_version_checked_at"
        ),
    }


def _lookup(data: dict[str, Any], metadata: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
        if name in metadata and metadata[name] is not None:
            return metadata[name]
    return None


def _first_string(data: dict[str, Any], metadata: dict[str, Any], *names: str) -> str | None:
    value = _lookup(data, metadata, *names)
    return value if isinstance(value, str) and value.strip() else None


def _first_bool(
    data: dict[str, Any], metadata: dict[str, Any], name: str, *, default: bool
) -> bool:
    value = _lookup(data, metadata, name)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise BulkIngestionError(f"{name} must be a boolean")
    return value


def _first_positive_int(data: dict[str, Any], metadata: dict[str, Any], *names: str) -> int | None:
    for name in names:
        value = _lookup(data, metadata, name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise BulkIngestionError(f"{name} must be an integer")
        if value >= 1:
            return value
    return None


def _first_string_list(data: dict[str, Any], metadata: dict[str, Any], name: str) -> list[str]:
    value = _lookup(data, metadata, name)
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise BulkIngestionError(f"{name} must be an array of strings")
    return value


def _validate_vector(value: Any, dimension: int) -> None:
    if not isinstance(value, list | tuple) or len(value) != dimension:
        raise BulkIngestionError(f"embedding vector must contain exactly {dimension} values")
    if any(
        isinstance(item, bool)
        or not isinstance(item, int | float)
        or not math.isfinite(float(item))
        for item in value
    ):
        raise BulkIngestionError("embedding vector values must be finite numbers")


def _require_staging_resource(value: str) -> None:
    normalized = value.casefold()
    if "staging" not in normalized or "production" in normalized or "prod" in normalized:
        raise BulkIngestionError("bulk ingestion is restricted to staging resources")
