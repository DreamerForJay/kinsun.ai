from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Mapping
from typing import Protocol, cast

import boto3

from agent_runtime.rag.models import QueryEmbeddingSettings


class QueryEmbeddingError(RuntimeError):
    """The query embedding could not be produced or validated."""


class BedrockRuntimeClient(Protocol):
    def invoke_model(self, **kwargs: object) -> Mapping[str, object]: ...


class QueryEmbedder(Protocol):
    @property
    def dimension(self) -> int: ...

    async def embed_query(self, text: str) -> list[float]: ...


class BedrockQueryEmbedder:
    """Cohere Embed v4 query adapter with an injected boto3-compatible client."""

    def __init__(
        self,
        client: BedrockRuntimeClient,
        settings: QueryEmbeddingSettings,
    ) -> None:
        self._client = client
        self._settings = settings

    @property
    def dimension(self) -> int:
        return self._settings.dimension

    async def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise QueryEmbeddingError("query text cannot be blank")
        request_body = {
            "texts": [text],
            "input_type": "search_query",
            "embedding_types": ["float"],
            "output_dimension": self._settings.dimension,
        }
        response = await asyncio.to_thread(
            self._client.invoke_model,
            modelId=self._settings.model_id,
            body=json.dumps(request_body).encode("utf-8"),
            contentType="application/json",
            accept="application/json",
        )
        if inspect.isawaitable(response):
            response = await response
        payload = _decode_response(response)
        vector = _extract_first_float_embedding(payload)
        if len(vector) != self._settings.dimension:
            raise QueryEmbeddingError(
                f"expected {self._settings.dimension} dimensions, got {len(vector)}"
            )
        return vector


def build_bedrock_client(settings: QueryEmbeddingSettings) -> BedrockRuntimeClient:
    """Create a real Bedrock Runtime client via the standard AWS credential chain."""

    session = boto3.Session(region_name=settings.region)
    return cast(
        BedrockRuntimeClient,
        session.client("bedrock-runtime", region_name=settings.region),
    )


def build_bedrock_query_embedder(settings: QueryEmbeddingSettings) -> BedrockQueryEmbedder:
    return BedrockQueryEmbedder(build_bedrock_client(settings), settings)


def _decode_response(response: Mapping[str, object]) -> Mapping[str, object]:
    body = response.get("body")
    if hasattr(body, "read"):
        body = body.read()
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    if isinstance(body, str):
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise QueryEmbeddingError("Bedrock returned invalid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise QueryEmbeddingError("Bedrock response must be a JSON object")
        return cast(Mapping[str, object], decoded)
    if isinstance(body, Mapping):
        return body
    if "embeddings" in response:
        return response
    raise QueryEmbeddingError("Bedrock response body is missing")


def _extract_first_float_embedding(payload: Mapping[str, object]) -> list[float]:
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, Mapping):
        embeddings = embeddings.get("float")
    if not isinstance(embeddings, list) or not embeddings:
        raise QueryEmbeddingError("Bedrock response has no float embeddings")

    first = embeddings[0]
    if not isinstance(first, list) or not first:
        raise QueryEmbeddingError("Bedrock response embedding is malformed")
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in first):
        raise QueryEmbeddingError("Bedrock response embedding contains non-numeric values")
    return [float(value) for value in first]
