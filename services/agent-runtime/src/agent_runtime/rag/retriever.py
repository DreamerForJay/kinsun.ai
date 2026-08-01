from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from agent_runtime.rag.client import OpenSearchClient, build_opensearch_client
from agent_runtime.rag.fallback import failed_response, no_data_response
from agent_runtime.rag.filters import is_normal_rag_eligible
from agent_runtime.rag.hybrid_search import HybridSearch
from agent_runtime.rag.models import (
    QueryProfile,
    RagRuntimeSettings,
    RetrievalRequestV1,
    RetrievalResponseV1,
    RetrievalResultV1,
)
from agent_runtime.rag.query_embedder import QueryEmbedder, build_bedrock_query_embedder


class Retriever:
    """Bounded staging retrieval flow with fail-closed source handling."""

    def __init__(
        self,
        *,
        query_embedder: QueryEmbedder,
        search_client: OpenSearchClient,
        hybrid_search: HybridSearch,
    ) -> None:
        self._query_embedder = query_embedder
        self._search_client = search_client
        self._hybrid_search = hybrid_search

    async def retrieve(self, request: RetrievalRequestV1) -> RetrievalResponseV1:
        try:
            vector = await self._query_embedder.embed_query(request.query)
            if len(vector) != self._query_embedder.dimension:
                raise ValueError("query embedding has an unexpected dimension")
            plan = self._hybrid_search.build(request, vector)
            hits = await self._search_client.search(plan)
        except Exception:
            # The public fallback deliberately excludes provider details and query text.
            return failed_response(request.request_id)

        results = _eligible_unique_results(
            _above_relevance_floor(hits, plan.min_score),
            request.top_k,
            request.query_profile,
            audience=request.audience,
            purpose=request.purpose,
        )
        if not results:
            return no_data_response(request.request_id)
        if len(results) < 3:
            return no_data_response(request.request_id, insufficient=True)
        return RetrievalResponseV1(
            schema_version="1.0.0",
            request_id=request.request_id,
            status="SUCCESS",
            fallback_message=None,
            results=results,
        )


def build_retriever(settings: RagRuntimeSettings) -> Retriever:
    """Compose the real staging Bedrock and OpenSearch adapters from validated settings."""

    return Retriever(
        query_embedder=build_bedrock_query_embedder(settings.embedding),
        search_client=build_opensearch_client(settings.opensearch),
        hybrid_search=HybridSearch(settings.hybrid),
    )


def _above_relevance_floor(
    hits: list[Mapping[str, object]], min_score: float
) -> list[Mapping[str, object]]:
    """Drop hits the configured floor rejects, so a bad query yields NO_DATA.

    The floor applies to the pipeline-normalized hybrid score, not to raw
    cosine similarity: the collection's knn clause accepts only ``k``, so it
    always returns that many neighbours no matter how poor the match. Without
    this, a query matching nothing still produced five cited chunks reported as
    SUCCESS. A hit that satisfies only one retrieval leg cannot exceed that
    leg's configured weight, which is what keeps unmatched queries below the
    floor.
    """

    scored: list[Mapping[str, object]] = []
    for hit in hits:
        score = hit.get("_score")
        if isinstance(score, bool) or not isinstance(score, int | float):
            continue
        if float(score) >= min_score:
            scored.append(hit)
    return scored


def _eligible_unique_results(
    hits: list[Mapping[str, object]],
    top_k: int,
    profile: QueryProfile,
    *,
    audience: str | None,
    purpose: str | None,
) -> list[RetrievalResultV1]:
    results: list[RetrievalResultV1] = []
    seen: set[str] = set()
    for hit in hits:
        source = hit.get("_source")
        if not isinstance(source, Mapping) or not is_normal_rag_eligible(
            source,
            profile,
            audience=audience,
            purpose=purpose,
        ):
            continue
        chunk_id = source.get("chunk_id")
        if not isinstance(chunk_id, str) or chunk_id in seen:
            continue
        try:
            result = RetrievalResultV1(
                chunk_id=chunk_id,
                text=source.get("text"),
                score=float(hit.get("_score", 0.0)),
                document_name=source.get("document_name"),
                section=source.get("section"),
                page_start=source.get("page_start"),
                page_end=source.get("page_end"),
                source_url=source.get("source_url"),
            )
        except (TypeError, ValueError, ValidationError):
            # Missing citation/policy metadata cannot enter agent context.
            continue
        seen.add(chunk_id)
        results.append(result)
        if len(results) == top_k:
            break
    return results
