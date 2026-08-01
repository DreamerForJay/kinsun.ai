"""Cohere Embed v4 adapter and external-only embedding artifact storage."""

from __future__ import annotations

import json
import math
import os
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from rag_ingestion.allowlist import Allowlist
from rag_ingestion.settings import (
    REQUIRED_EMBEDDING_DIMENSION,
    ensure_artifact_outside_repository,
)
from rag_ingestion.validator import ValidatedChunk


class BedrockRuntimeClient(Protocol):
    def invoke_model(self, **kwargs: Any) -> dict[str, Any]: ...


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be safely generated or loaded."""


class EmbeddingBatchError(EmbeddingError):
    def __init__(self, message: str, *, success_count: int, failure_count: int) -> None:
        self.success_count = success_count
        self.failure_count = failure_count
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    success_count: int
    failure_count: int


class BedrockEmbedder:
    """Injectable Bedrock adapter for document embeddings."""

    def __init__(
        self,
        client: BedrockRuntimeClient,
        *,
        model_id: str,
        dimension: int,
        batch_size: int = 96,
        truncate: str = "NONE",
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id is required")
        if dimension != REQUIRED_EMBEDDING_DIMENSION:
            raise ValueError(f"embedding dimension must be {REQUIRED_EMBEDDING_DIMENSION}")
        if not 1 <= batch_size <= 96:
            raise ValueError("batch_size must be between 1 and 96")
        normalized_truncate = truncate.upper()
        if normalized_truncate not in {"NONE", "LEFT", "RIGHT"}:
            raise ValueError("truncate must be NONE, LEFT, or RIGHT")
        self._client = client
        self.model_id = model_id
        self.dimension = dimension
        self.batch_size = batch_size
        self.truncate = normalized_truncate

    @classmethod
    def from_boto3(
        cls,
        *,
        region: str,
        model_id: str,
        dimension: int,
        batch_size: int = 96,
        truncate: str = "NONE",
        session: Any | None = None,
    ) -> BedrockEmbedder:
        if not region.strip():
            raise ValueError("AWS region is required")
        if session is None:
            import boto3

            session = boto3.Session()
        client = session.client("bedrock-runtime", region_name=region)
        return cls(
            client,
            model_id=model_id,
            dimension=dimension,
            batch_size=batch_size,
            truncate=truncate,
        )

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingResult:
        if not texts:
            raise EmbeddingError("at least one document is required")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise EmbeddingError("all embedding inputs must be non-empty strings")

        vectors: list[tuple[float, ...]] = []
        total = len(texts)
        for offset in range(0, total, self.batch_size):
            batch = list(texts[offset : offset + self.batch_size])
            request_body = {
                "texts": batch,
                "input_type": "search_document",
                "embedding_types": ["float"],
                "output_dimension": self.dimension,
                "truncate": self.truncate,
            }
            try:
                response = self._client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(request_body, ensure_ascii=False),
                    accept="application/json",
                    contentType="application/json",
                )
                parsed_vectors = _parse_response_vectors(response, self.dimension)
                if len(parsed_vectors) != len(batch):
                    raise EmbeddingError("Bedrock response vector count does not match request")
                vectors.extend(parsed_vectors)
            except Exception as exc:
                if isinstance(exc, EmbeddingBatchError):
                    raise
                raise EmbeddingBatchError(
                    f"embedding batch failed: {type(exc).__name__}",
                    success_count=len(vectors),
                    failure_count=total - len(vectors),
                ) from exc
        return EmbeddingResult(
            vectors=tuple(vectors),
            success_count=len(vectors),
            failure_count=0,
        )


def generate_embedding_artifact(
    *,
    allowlist: Allowlist,
    expected_allowlist_sha256: str | None,
    rag_mode: str,
    require_owner_signature: bool,
    production_enabled: bool,
    embedder: BedrockEmbedder,
    chunks: Sequence[ValidatedChunk],
    artifact_path: Path,
    repository_root: Path,
) -> EmbeddingResult:
    """Generate all vectors before atomically publishing an external artifact."""

    allowlist.assert_effective_for_execution(
        expected_allowlist_sha256,
        mode=rag_mode,
        require_owner_signature=require_owner_signature,
        production_enabled=production_enabled,
    )
    if rag_mode != "staging" or production_enabled:
        raise EmbeddingError("this ingestion service release can only execute staging targets")
    safe_path = ensure_artifact_outside_repository(artifact_path, repository_root)
    result = embedder.embed_documents([chunk.embedding_text for chunk in chunks])
    rows = [
        {
            "record_type": "manifest",
            "schema_version": "1.0.0",
            "allowlist_sha256": allowlist.sha256,
            "embedding_model_id": embedder.model_id,
            "embedding_dimension": embedder.dimension,
            "chunk_count": len(chunks),
        },
        *[
            {
                "record_type": "embedding",
                "chunk_id": chunk.chunk_id,
                "embedding_text_sha256": chunk.embedding_text_sha256,
                "allowlist_sha256": allowlist.sha256,
                "embedding_model_id": embedder.model_id,
                "embedding_dimension": embedder.dimension,
                "embedding": list(vector),
            }
            for chunk, vector in zip(chunks, result.vectors, strict=True)
        ],
    ]
    _atomic_write_jsonl(safe_path, rows)
    return result


def read_embedding_artifact(
    *,
    allowlist: Allowlist,
    model_id: str,
    artifact_path: Path,
    repository_root: Path,
    chunks: Sequence[ValidatedChunk],
    dimension: int,
) -> dict[str, tuple[float, ...]]:
    safe_path = ensure_artifact_outside_repository(artifact_path, repository_root)
    if dimension != REQUIRED_EMBEDDING_DIMENSION:
        raise EmbeddingError(f"embedding dimension must be {REQUIRED_EMBEDDING_DIMENSION}")
    expected = {chunk.chunk_id: chunk for chunk in chunks}
    vectors: dict[str, tuple[float, ...]] = {}
    try:
        handle = safe_path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise EmbeddingError(f"cannot read embedding artifact: {type(exc).__name__}") from exc
    with handle:
        manifest_line = handle.readline()
        manifest = _parse_artifact_row(manifest_line, 1)
        _validate_artifact_manifest(
            manifest,
            allowlist=allowlist,
            model_id=model_id,
            dimension=dimension,
            chunk_count=len(expected),
        )
        for line_number, line in enumerate(handle, start=2):
            if not line.strip():
                raise EmbeddingError(f"blank embedding artifact line: {line_number}")
            row = _parse_artifact_row(line, line_number)
            expected_keys = {
                "record_type",
                "chunk_id",
                "embedding_text_sha256",
                "allowlist_sha256",
                "embedding_model_id",
                "embedding_dimension",
                "embedding",
            }
            if set(row) != expected_keys or row.get("record_type") != "embedding":
                raise EmbeddingError(f"embedding artifact row shape is invalid: {line_number}")
            if row.get("allowlist_sha256") != allowlist.sha256:
                raise EmbeddingError(f"embedding artifact allowlist mismatch: {line_number}")
            if row.get("embedding_model_id") != model_id:
                raise EmbeddingError(f"embedding artifact model mismatch: {line_number}")
            if row.get("embedding_dimension") != dimension:
                raise EmbeddingError(f"embedding artifact dimension mismatch: {line_number}")
            chunk_id = row.get("chunk_id")
            if not isinstance(chunk_id, str) or chunk_id not in expected:
                raise EmbeddingError(
                    f"embedding artifact has an unexpected chunk_id: {line_number}"
                )
            if chunk_id in vectors:
                raise EmbeddingError(f"embedding artifact has duplicate chunk_id: {chunk_id}")
            if row.get("embedding_text_sha256") != expected[chunk_id].embedding_text_sha256:
                raise EmbeddingError(f"embedding artifact hash mismatch for {chunk_id}")
            vectors[chunk_id] = _validate_vector(row.get("embedding"), dimension)
    missing = set(expected) - set(vectors)
    if missing:
        raise EmbeddingError(f"embedding artifact is missing {len(missing)} chunks")
    return vectors


def _parse_artifact_row(line: str, line_number: int) -> dict[str, Any]:
    if not line.strip():
        raise EmbeddingError(f"missing embedding artifact row: {line_number}")
    try:
        row = json.loads(line)
    except json.JSONDecodeError as exc:
        raise EmbeddingError(f"invalid embedding artifact JSON: {line_number}") from exc
    if not isinstance(row, dict):
        raise EmbeddingError(f"embedding artifact row must be an object: {line_number}")
    return row


def _validate_artifact_manifest(
    manifest: dict[str, Any],
    *,
    allowlist: Allowlist,
    model_id: str,
    dimension: int,
    chunk_count: int,
) -> None:
    expected_keys = {
        "record_type",
        "schema_version",
        "allowlist_sha256",
        "embedding_model_id",
        "embedding_dimension",
        "chunk_count",
    }
    if set(manifest) != expected_keys or manifest.get("record_type") != "manifest":
        raise EmbeddingError("embedding artifact manifest shape is invalid")
    if manifest.get("schema_version") != "1.0.0":
        raise EmbeddingError("embedding artifact schema version is unsupported")
    if manifest.get("allowlist_sha256") != allowlist.sha256:
        raise EmbeddingError("embedding artifact manifest allowlist mismatch")
    if manifest.get("embedding_model_id") != model_id:
        raise EmbeddingError("embedding artifact manifest model mismatch")
    if manifest.get("embedding_dimension") != dimension:
        raise EmbeddingError("embedding artifact manifest dimension mismatch")
    if manifest.get("chunk_count") != chunk_count:
        raise EmbeddingError("embedding artifact manifest chunk count mismatch")


def _parse_response_vectors(
    response: dict[str, Any], dimension: int
) -> tuple[tuple[float, ...], ...]:
    body: Any = response.get("body", response)
    if hasattr(body, "read"):
        body = body.read()
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError as exc:
            raise EmbeddingError("Bedrock response body is not JSON") from exc
    if not isinstance(body, dict):
        raise EmbeddingError("Bedrock response body must be an object")
    embeddings = body.get("embeddings")
    if isinstance(embeddings, dict):
        embeddings = embeddings.get("float")
    if not isinstance(embeddings, list):
        raise EmbeddingError("Bedrock response is missing float embeddings")
    return tuple(_validate_vector(vector, dimension) for vector in embeddings)


def _validate_vector(value: Any, dimension: int) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != dimension:
        raise EmbeddingError(f"embedding vector must contain exactly {dimension} values")
    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int | float):
            raise EmbeddingError("embedding vector values must be numeric")
        converted = float(item)
        if not math.isfinite(converted):
            raise EmbeddingError("embedding vector values must be finite")
        vector.append(converted)
    return tuple(vector)


def _atomic_write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
