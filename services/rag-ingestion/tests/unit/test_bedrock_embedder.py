from __future__ import annotations

import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from conftest import write_dataset

from rag_ingestion.allowlist import Allowlist, load_allowlist
from rag_ingestion.bedrock_embedder import (
    BedrockEmbedder,
    EmbeddingBatchError,
    EmbeddingError,
    generate_embedding_artifact,
    read_embedding_artifact,
)
from rag_ingestion.chunk_loader import load_allowlisted_chunks
from rag_ingestion.settings import SettingsError
from rag_ingestion.validator import ValidatedChunk, validate_chunks

DIMENSION = 1024


class FakeBedrockClient:
    def __init__(self, *, by_type: bool = False, dimension: int = DIMENSION) -> None:
        self.by_type = by_type
        self.dimension = dimension
        self.requests: list[dict[str, Any]] = []

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        request = json.loads(kwargs["body"])
        vectors = [[float(index % 7) for index in range(self.dimension)] for _ in request["texts"]]
        embeddings: Any = {"float": vectors} if self.by_type else vectors
        body = io.BytesIO(json.dumps({"embeddings": embeddings}).encode())
        return {"body": body}


@pytest.mark.parametrize("by_type", [False, True])
def test_embedder_uses_cohere_v4_document_shape_and_parses_both_responses(
    by_type: bool,
) -> None:
    client = FakeBedrockClient(by_type=by_type)
    embedder = BedrockEmbedder(
        client,
        model_id="configured-model-id",
        dimension=DIMENSION,
    )

    result = embedder.embed_documents(["synthetic document"])

    request = json.loads(client.requests[0]["body"])
    assert request == {
        "texts": ["synthetic document"],
        "input_type": "search_document",
        "embedding_types": ["float"],
        "output_dimension": 1024,
        "truncate": "NONE",
    }
    assert client.requests[0]["modelId"] == "configured-model-id"
    assert len(result.vectors[0]) == DIMENSION


def test_wrong_vector_dimension_fails_entire_embedding_run() -> None:
    embedder = BedrockEmbedder(
        FakeBedrockClient(dimension=DIMENSION - 1),
        model_id="configured-model-id",
        dimension=DIMENSION,
    )

    with pytest.raises(EmbeddingBatchError) as raised:
        embedder.embed_documents(["synthetic document"])

    assert raised.value.success_count == 0
    assert raised.value.failure_count == 1


def test_external_embedding_artifact_round_trip(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset")
    allowlist = load_allowlist(manifest_path)
    chunks = validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist).chunks
    artifact = tmp_path / "external" / "embeddings.jsonl"
    result = generate_embedding_artifact(
        allowlist=allowlist,
        expected_allowlist_sha256=allowlist.sha256,
        rag_mode="staging",
        require_owner_signature=False,
        production_enabled=False,
        embedder=BedrockEmbedder(
            FakeBedrockClient(), model_id="configured-model-id", dimension=DIMENSION
        ),
        chunks=chunks,
        artifact_path=artifact,
        repository_root=repository_root,
    )

    loaded = read_embedding_artifact(
        allowlist=allowlist,
        model_id="configured-model-id",
        artifact_path=artifact,
        repository_root=repository_root,
        chunks=chunks,
        dimension=DIMENSION,
    )

    assert result.success_count == 1
    assert len(loaded[chunks[0].chunk_id]) == DIMENSION


def test_embedding_artifact_inside_repo_is_rejected(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    with pytest.raises(SettingsError, match="inside the repository"):
        read_embedding_artifact(
            allowlist=load_allowlist(write_dataset(tmp_path / "dataset")[0]),
            model_id="configured-model-id",
            artifact_path=repository_root / "vectors.jsonl",
            repository_root=repository_root,
            chunks=[],
            dimension=DIMENSION,
        )


def test_embedding_artifact_rejects_model_mismatch(tmp_path: Path) -> None:
    allowlist, chunks, artifact, repository_root = _generated_artifact(tmp_path)

    with pytest.raises(EmbeddingError, match="model mismatch"):
        read_embedding_artifact(
            allowlist=allowlist,
            model_id="different-model-id",
            artifact_path=artifact,
            repository_root=repository_root,
            chunks=chunks,
            dimension=DIMENSION,
        )


def test_embedding_artifact_rejects_allowlist_mismatch(tmp_path: Path) -> None:
    allowlist, chunks, artifact, repository_root = _generated_artifact(tmp_path)
    different_allowlist = replace(allowlist, sha256="0" * 64)

    with pytest.raises(EmbeddingError, match="allowlist mismatch"):
        read_embedding_artifact(
            allowlist=different_allowlist,
            model_id="configured-model-id",
            artifact_path=artifact,
            repository_root=repository_root,
            chunks=chunks,
            dimension=DIMENSION,
        )


def test_embedding_artifact_rejects_dimension_mismatch_in_manifest(tmp_path: Path) -> None:
    allowlist, chunks, artifact, repository_root = _generated_artifact(tmp_path)
    lines = artifact.read_text(encoding="utf-8").splitlines()
    manifest = json.loads(lines[0])
    manifest["embedding_dimension"] = 1536
    lines[0] = json.dumps(manifest)
    artifact.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        read_embedding_artifact(
            allowlist=allowlist,
            model_id="configured-model-id",
            artifact_path=artifact,
            repository_root=repository_root,
            chunks=chunks,
            dimension=DIMENSION,
        )


def _generated_artifact(
    tmp_path: Path,
) -> tuple[Allowlist, tuple[ValidatedChunk, ...], Path, Path]:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    manifest_path, chunks_dir = write_dataset(tmp_path / "dataset")
    allowlist = load_allowlist(manifest_path)
    chunks = validate_chunks(load_allowlisted_chunks(chunks_dir, allowlist), allowlist).chunks
    artifact = tmp_path / "external" / "embeddings.jsonl"
    generate_embedding_artifact(
        allowlist=allowlist,
        expected_allowlist_sha256=allowlist.sha256,
        rag_mode="staging",
        require_owner_signature=False,
        production_enabled=False,
        embedder=BedrockEmbedder(
            FakeBedrockClient(), model_id="configured-model-id", dimension=DIMENSION
        ),
        chunks=chunks,
        artifact_path=artifact,
        repository_root=repository_root,
    )
    return allowlist, chunks, artifact, repository_root
