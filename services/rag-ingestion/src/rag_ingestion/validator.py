"""Hash and field validation performed before any external call."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from rag_ingestion.allowlist import SHA256_PATTERN, Allowlist, AllowlistEntry
from rag_ingestion.chunk_loader import LoadedChunk


class ChunkValidationError(ValueError):
    """Raised with safe locations/IDs, never rejected text."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


@dataclass(frozen=True, slots=True)
class ValidatedChunk:
    loaded: LoadedChunk
    allowlist_entry: AllowlistEntry
    text_sha256: str
    embedding_text_sha256: str

    @property
    def data(self) -> dict[str, Any]:
        return self.loaded.data

    @property
    def chunk_id(self) -> str:
        return self.allowlist_entry.chunk_id

    @property
    def text(self) -> str:
        return self.data["text"]

    @property
    def embedding_text(self) -> str:
        return self.data["embedding_text"]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    chunks: tuple[ValidatedChunk, ...]
    source_count: int
    chunk_count: int
    allowlist_effective: bool


def validate_chunks(
    loaded_chunks: tuple[LoadedChunk, ...] | list[LoadedChunk],
    allowlist: Allowlist,
) -> ValidationResult:
    """Validate every record and return only if the full set is valid."""

    entries = allowlist.entry_by_chunk_id
    errors: list[str] = []
    validated: list[ValidatedChunk] = []
    seen: set[str] = set()
    sources: set[str] = set()
    for loaded in loaded_chunks:
        location = f"{loaded.file_path.name}:{loaded.line_number}"
        chunk_id = loaded.chunk_id
        if chunk_id in seen:
            errors.append(f"duplicate chunk_id {chunk_id} at {location}")
            continue
        seen.add(chunk_id)
        entry = entries.get(chunk_id)
        if entry is None:
            errors.append(f"chunk_id outside allowlist at {location}")
            continue
        data = loaded.data
        actual_chunk_index = data.get("chunk_index")
        if (
            isinstance(actual_chunk_index, bool)
            or not isinstance(actual_chunk_index, int)
            or actual_chunk_index != entry.chunk_index
        ):
            errors.append(f"chunk_index does not match allowlist for {chunk_id}")
        text = data.get("text")
        embedding_text = data.get("embedding_text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"text missing or blank for {chunk_id}")
            continue
        if not isinstance(embedding_text, str) or not embedding_text.strip():
            errors.append(f"embedding_text missing or blank for {chunk_id}")
            continue

        text_sha256 = _sha256_text(text)
        embedding_text_sha256 = _sha256_text(embedding_text)
        if text_sha256 != entry.text_sha256:
            errors.append(f"text hash mismatch for {chunk_id}")
        if embedding_text_sha256 != entry.embedding_text_sha256:
            errors.append(f"embedding_text hash mismatch for {chunk_id}")
        _validate_declared_hashes(data, chunk_id, text_sha256, embedding_text_sha256, errors)

        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            errors.append(f"metadata must be an object for {chunk_id}")
        source_id = data.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(f"source_id missing or blank for {chunk_id}")
        else:
            sources.add(source_id)
            if entry.source_id is not None and entry.source_id != source_id:
                errors.append(f"source_id does not match allowlist for {chunk_id}")

        validated.append(
            ValidatedChunk(
                loaded=loaded,
                allowlist_entry=entry,
                text_sha256=text_sha256,
                embedding_text_sha256=embedding_text_sha256,
            )
        )

    expected_ids = set(allowlist.allowed_chunk_ids)
    missing = expected_ids - seen
    extra = seen - expected_ids
    if missing:
        errors.append(f"{len(missing)} allowlisted chunk_id values are missing")
    if extra:
        errors.append(f"{len(extra)} chunk_id values are outside the allowlist")
    if len(loaded_chunks) != allowlist.declared_chunk_count:
        errors.append("loaded chunk count does not match allowlist")
    if len(sources) != allowlist.declared_source_count:
        errors.append("loaded source count does not match allowlist")
    if errors:
        raise ChunkValidationError(errors)
    return ValidationResult(
        chunks=tuple(validated),
        source_count=len(sources),
        chunk_count=len(validated),
        allowlist_effective=allowlist.governance.effective,
    )


def _validate_declared_hashes(
    data: dict[str, Any],
    chunk_id: str,
    text_sha256: str,
    embedding_text_sha256: str,
    errors: list[str],
) -> None:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    for container in (data, metadata):
        _check_optional_hash(container, "text_sha256", text_sha256, chunk_id, errors)
        _check_optional_hash(
            container,
            "embedding_text_sha256",
            embedding_text_sha256,
            chunk_id,
            errors,
        )
        _check_optional_hash(
            container,
            "embedding_text_hash",
            embedding_text_sha256,
            chunk_id,
            errors,
        )


def _check_optional_hash(
    container: dict[str, Any],
    key: str,
    expected: str,
    chunk_id: str,
    errors: list[str],
) -> None:
    value = container.get(key)
    if value is None:
        return
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value) or value != expected:
        errors.append(f"declared {key} mismatch for {chunk_id}")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
