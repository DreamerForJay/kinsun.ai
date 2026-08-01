from __future__ import annotations

from agent_runtime.rag.filters import build_normal_rag_filter
from agent_runtime.rag.models import HybridSearchPlan, HybridSearchSettings, RetrievalRequestV1


class HybridSearch:
    """Build a bounded query from approved parameters and profile configuration."""

    def __init__(self, settings: HybridSearchSettings) -> None:
        self._settings = settings

    def build(self, request: RetrievalRequestV1, query_vector: list[float]) -> HybridSearchPlan:
        profile = self._settings.for_profile(request.query_profile)
        body: dict[str, object] = {
            "size": request.top_k,
            "_source": [
                "chunk_id",
                "text",
                "document_name",
                "section",
                "page_start",
                "page_end",
                "source_url",
                "current_status",
                "stop_normal_rag",
                "risk_level",
                "allowed_audiences",
                "allowed_purposes",
            ],
            "query": {
                "hybrid": {
                    "queries": [
                        {"match": {"text": {"query": request.query}}},
                        {
                            "knn": {
                                "embedding": {
                                    "vector": query_vector,
                                    # Serverless accepts only `k` here. It rejects
                                    # min_score and max_distance alike with "[knn]
                                    # requires exactly one of k, distance or score
                                    # to be set", so profile.vector_min_score cannot
                                    # be enforced on the vector leg. Sufficiency is
                                    # decided by Retriever's minimum eligible count.
                                    "k": request.top_k,
                                }
                            }
                        },
                    ],
                    "filter": build_normal_rag_filter(
                        profile=request.query_profile,
                        audience=request.audience,
                        purpose=request.purpose,
                    ),
                }
            },
        }
        return HybridSearchPlan(
            index_alias=self._settings.index_alias,
            search_pipeline=profile.search_pipeline,
            profile=profile.profile,
            bm25_weight=profile.bm25_weight,
            vector_weight=profile.vector_weight,
            min_score=profile.vector_min_score,
            body=body,
        )
