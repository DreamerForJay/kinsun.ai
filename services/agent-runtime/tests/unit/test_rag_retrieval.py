from __future__ import annotations

import json
from pathlib import Path

import pytest

import agent_runtime.rag.client as opensearch_module
import agent_runtime.rag.query_embedder as embedder_module
from agent_runtime.rag.citations import render_cited_chunk
from agent_runtime.rag.client import OpenSearchClient, build_opensearch_transport
from agent_runtime.rag.fallback import NO_DATA_MESSAGE
from agent_runtime.rag.filters import is_normal_rag_eligible
from agent_runtime.rag.hybrid_search import HybridSearch
from agent_runtime.rag.models import (
    HybridProfileSettings,
    HybridSearchSettings,
    OpenSearchConnectionSettings,
    QueryEmbeddingSettings,
    RagRuntimeSettings,
    RetrievalRequestV1,
)
from agent_runtime.rag.query_embedder import (
    BedrockQueryEmbedder,
    QueryEmbeddingError,
    build_bedrock_client,
)
from agent_runtime.rag.retriever import Retriever


def make_profile(name: str) -> HybridProfileSettings:
    weights = (0.65, 0.35) if name == "legal" else (0.4, 0.6)
    return HybridProfileSettings(
        profile=name,
        search_pipeline=f"pipeline-{name}",
        bm25_weight=weights[0],
        vector_weight=weights[1],
        vector_min_score=0.7,
        top_k=5,
        agent_chunk_min=3,
        agent_chunk_max=5,
    )


def make_search_settings() -> HybridSearchSettings:
    return HybridSearchSettings(
        index_alias="rag-staging-current",
        natural_language=make_profile("natural_language"),
        legal=make_profile("legal"),
    )


def make_request(
    profile: str = "natural_language",
    *,
    audience: str | None = None,
    purpose: str | None = None,
) -> RetrievalRequestV1:
    return RetrievalRequestV1(
        schema_version="1.0.0",
        request_id=f"request-{profile}",
        query="長照服務如何申請？",
        query_profile=profile,
        top_k=5,
        audience=audience,
        purpose=purpose,
        language="zh-TW",
    )


def make_hit(
    chunk_id: str,
    *,
    stop_normal_rag: bool = False,
    current_status: str = "current",
    risk_level: str = "low",
    score: float = 1.0,
    allowed_audiences: list[str] | None = None,
    allowed_purposes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "_id": chunk_id,
        "_score": score,
        "_source": {
            "chunk_id": chunk_id,
            "text": f"合成測試內容 {chunk_id}",
            "document_name": "合成長照指引",
            "section": "申請流程",
            "page_start": 10,
            "page_end": 11,
            "source_url": "https://example.test/guide",
            "current_status": current_status,
            "stop_normal_rag": stop_normal_rag,
            "risk_level": risk_level,
            "allowed_audiences": allowed_audiences,
            "allowed_purposes": allowed_purposes,
        },
    }


class FakeBedrockRuntime:
    def __init__(self, dimension: int = 1024) -> None:
        self.dimension = dimension
        self.kwargs: dict[str, object] | None = None

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        self.kwargs = kwargs
        body = json.dumps({"embeddings": {"float": [[0.01] * self.dimension]}})
        return {"body": body.encode("utf-8")}


class FakeQueryEmbedder:
    dimension = 1024

    async def embed_query(self, text: str) -> list[float]:
        return [0.01] * 1024


class WrongDimensionQueryEmbedder:
    dimension = 1024

    async def embed_query(self, text: str) -> list[float]:
        return [0.01] * 3


class FakeOpenSearchTransport:
    def __init__(self, hits: list[dict[str, object]]) -> None:
        self.hits = hits
        self.kwargs: dict[str, object] | None = None

    def search(self, **kwargs: object) -> dict[str, object]:
        self.kwargs = kwargs
        return {"hits": {"hits": self.hits}}


class FakeAwsSession:
    def __init__(self, *, region_name: str) -> None:
        self.region_name = region_name

    def client(self, service_name: str, *, region_name: str):
        return {"service_name": service_name, "region_name": region_name}

    def get_credentials(self):
        return object()


def make_retriever(transport: FakeOpenSearchTransport) -> Retriever:
    return Retriever(
        query_embedder=FakeQueryEmbedder(),
        search_client=OpenSearchClient(transport),
        hybrid_search=HybridSearch(make_search_settings()),
    )


@pytest.mark.asyncio
async def test_bedrock_query_embedder_uses_search_query_and_configured_model() -> None:
    runtime = FakeBedrockRuntime()
    embedder = BedrockQueryEmbedder(
        runtime,
        QueryEmbeddingSettings(
            model_id="configured-embed-model",
            region="configured-region",
            dimension=1024,
        ),
    )

    vector = await embedder.embed_query("我要怎麼申請長照？")

    assert len(vector) == 1024
    assert runtime.kwargs is not None
    assert runtime.kwargs["modelId"] == "configured-embed-model"
    body = json.loads(runtime.kwargs["body"])
    assert body["input_type"] == "search_query"
    assert body["output_dimension"] == 1024
    assert body["embedding_types"] == ["float"]


@pytest.mark.asyncio
async def test_query_embedding_with_wrong_dimension_fails_closed() -> None:
    embedder = BedrockQueryEmbedder(
        FakeBedrockRuntime(dimension=3),
        QueryEmbeddingSettings(model_id="model", region="region", dimension=1024),
    )

    with pytest.raises(QueryEmbeddingError, match="expected 1024 dimensions"):
        await embedder.embed_query("測試查詢")


@pytest.mark.asyncio
async def test_retriever_rejects_wrong_dimension_from_replaceable_embedder() -> None:
    retriever = Retriever(
        query_embedder=WrongDimensionQueryEmbedder(),
        search_client=OpenSearchClient(FakeOpenSearchTransport([])),
        hybrid_search=HybridSearch(make_search_settings()),
    )

    response = await retriever.retrieve(make_request())

    assert response.status == "FAILED"
    assert response.results == []
    assert "不產生" in response.fallback_message


def test_bedrock_factory_uses_configured_region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embedder_module.boto3, "Session", FakeAwsSession)
    settings = QueryEmbeddingSettings(
        model_id="configured-model",
        region="configured-region",
        dimension=1024,
    )

    client = build_bedrock_client(settings)

    assert client == {
        "service_name": "bedrock-runtime",
        "region_name": "configured-region",
    }


def test_opensearch_factory_uses_sigv4_and_configured_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_signer(credentials: object, region: str, service: str):
        captured["signer"] = (credentials, region, service)
        return "signed-auth"

    def fake_opensearch(**kwargs: object):
        captured["client"] = kwargs
        return FakeOpenSearchTransport([])

    monkeypatch.setattr(opensearch_module.boto3, "Session", FakeAwsSession)
    monkeypatch.setattr(opensearch_module, "AWSV4SignerAuth", fake_signer)
    monkeypatch.setattr(opensearch_module, "OpenSearch", fake_opensearch)

    transport = build_opensearch_transport(
        OpenSearchConnectionSettings(
            host="https://collection-id.region.aoss.amazonaws.com",
            region="configured-region",
            index_name="configured-staging-index",
            index_alias="configured-staging-alias",
            mode="staging",
        )
    )

    assert isinstance(transport, FakeOpenSearchTransport)
    signer = captured["signer"]
    assert signer[1:] == ("configured-region", "aoss")
    client_kwargs = captured["client"]
    assert client_kwargs["hosts"] == [
        {"host": "collection-id.region.aoss.amazonaws.com", "port": 443}
    ]
    assert client_kwargs["http_auth"] == "signed-auth"


def test_runtime_settings_load_from_explicit_config_paths_and_environment() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    config_dir = repository_root / "config" / "rag"

    settings = RagRuntimeSettings.from_config_files(
        embedding_config_path=config_dir / "embedding.yaml",
        index_config_path=config_dir / "opensearch-index-v1.json",
        natural_profile_path=config_dir / "hybrid-natural-language.json",
        legal_profile_path=config_dir / "hybrid-legal.json",
        environ={
            "AWS_REGION": "configured-region",
            "BEDROCK_EMBEDDING_MODEL_ID": "configured-model",
            "BEDROCK_EMBEDDING_DIMENSION": "1024",
            "OPENSEARCH_HOST": "https://search.example.test",
            "OPENSEARCH_INDEX": "configured-staging-index",
            "OPENSEARCH_ALIAS": "configured-staging-alias",
            "RAG_MODE": "staging",
        },
    )

    assert settings.embedding.model_id == "configured-model"
    assert settings.embedding.region == "configured-region"
    assert settings.opensearch.host == "https://search.example.test"
    assert settings.opensearch.index_name == "configured-staging-index"
    assert settings.hybrid.index_alias == "configured-staging-alias"
    assert settings.hybrid.natural_language.bm25_weight == 0.4
    assert settings.hybrid.legal.vector_weight == 0.35
    assert settings.hybrid.natural_language.vector_min_score == 0.7


def test_runtime_settings_reject_production_index_or_alias() -> None:
    with pytest.raises(ValueError, match="explicitly staging"):
        OpenSearchConnectionSettings(
            host="https://search.example.test",
            region="configured-region",
            index_name="knowledge-production-v1",
            index_alias="knowledge-staging",
            mode="staging",
        )


@pytest.mark.parametrize(
    ("profile", "pipeline", "weights"),
    [
        ("natural_language", "pipeline-natural_language", (0.4, 0.6)),
        ("legal", "pipeline-legal", (0.65, 0.35)),
    ],
)
def test_hybrid_plan_uses_configured_profile_and_mandatory_filters(
    profile: str, pipeline: str, weights: tuple[float, float]
) -> None:
    plan = HybridSearch(make_search_settings()).build(make_request(profile), [0.0] * 1024)

    assert plan.search_pipeline == pipeline
    assert (plan.bm25_weight, plan.vector_weight) == weights
    assert plan.body["size"] == 5
    hybrid = plan.body["query"]["hybrid"]
    assert hybrid["queries"][0] == {"match": {"text": {"query": "長照服務如何申請？"}}}
    assert hybrid["queries"][1]["knn"]["embedding"]["min_score"] == 0.7
    assert "k" not in hybrid["queries"][1]["knn"]["embedding"]
    expected_bool: dict[str, object] = {
        "must": [
            {"term": {"current_status": "current"}},
            {"term": {"stop_normal_rag": False}},
            {"bool": {"must_not": [{"exists": {"field": "allowed_audiences"}}]}},
            {"bool": {"must_not": [{"exists": {"field": "allowed_purposes"}}]}},
        ],
        "must_not": [
            {"terms": {"risk_level": ["high", "critical", "high_red_line"]}},
        ],
    }
    assert hybrid["filter"] == {"bool": expected_bool}


def test_high_risk_query_filter_is_applied_to_every_normal_rag_profile() -> None:
    natural_plan = HybridSearch(make_search_settings()).build(
        make_request("natural_language"), [0.0] * 1024
    )
    legal_plan = HybridSearch(make_search_settings()).build(make_request("legal"), [0.0] * 1024)

    natural_bool = natural_plan.body["query"]["hybrid"]["filter"]["bool"]
    legal_bool = legal_plan.body["query"]["hybrid"]["filter"]["bool"]
    assert natural_bool["must_not"] == [
        {"terms": {"risk_level": ["high", "critical", "high_red_line"]}},
    ]
    assert legal_bool["must_not"] == natural_bool["must_not"]


def test_hybrid_plan_adds_parameterized_metadata_scope_filters() -> None:
    request = make_request(audience="elder", purpose="care_guidance")

    plan = HybridSearch(make_search_settings()).build(request, [0.0] * 1024)

    must = plan.body["query"]["hybrid"]["filter"]["bool"]["must"]
    assert {
        "bool": {
            "should": [
                {"term": {"allowed_audiences": "elder"}},
                {"bool": {"must_not": [{"exists": {"field": "allowed_audiences"}}]}},
            ],
            "minimum_should_match": 1,
        }
    } in must
    assert {
        "bool": {
            "should": [
                {"term": {"allowed_purposes": "care_guidance"}},
                {"bool": {"must_not": [{"exists": {"field": "allowed_purposes"}}]}},
            ],
            "minimum_should_match": 1,
        }
    } in must


@pytest.mark.asyncio
async def test_opensearch_uses_staging_alias_and_search_pipeline() -> None:
    transport = FakeOpenSearchTransport([])
    plan = HybridSearch(make_search_settings()).build(make_request(), [0.0] * 1024)

    await OpenSearchClient(transport).search(plan)

    assert transport.kwargs is not None
    assert transport.kwargs["index"] == "rag-staging-current"
    assert transport.kwargs["params"] == {"search_pipeline": "pipeline-natural_language"}


@pytest.mark.asyncio
async def test_no_results_returns_explicit_fallback_and_never_guesses() -> None:
    response = await make_retriever(FakeOpenSearchTransport([])).retrieve(make_request())

    assert response.status == "NO_DATA"
    assert response.results == []
    assert response.fallback_message == NO_DATA_MESSAGE
    assert "無法" in response.fallback_message


@pytest.mark.asyncio
async def test_stop_normal_rag_is_rejected_for_every_profile() -> None:
    for profile in ("natural_language", "legal"):
        hits = [make_hit(f"safe-{number}") for number in range(3)]
        hits.append(make_hit("blocked-stop", stop_normal_rag=True, score=99.0))
        response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(
            make_request(profile)
        )

        assert response.status == "SUCCESS"
        assert {result.chunk_id for result in response.results} == {
            "safe-0",
            "safe-1",
            "safe-2",
        }


@pytest.mark.asyncio
async def test_high_and_critical_risk_do_not_enter_natural_language_context() -> None:
    hits = [make_hit(f"safe-{number}") for number in range(3)]
    hits.extend(
        [
            make_hit("blocked-high", risk_level="high", score=99.0),
            make_hit("blocked-critical", risk_level="critical", score=100.0),
        ]
    )

    response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(make_request())

    assert response.status == "SUCCESS"
    assert {result.chunk_id for result in response.results} == {
        "safe-0",
        "safe-1",
        "safe-2",
    }
    assert is_normal_rag_eligible(hits[3]["_source"], "legal") is False


@pytest.mark.asyncio
async def test_metadata_scope_mismatch_is_rejected_after_search() -> None:
    hits = [make_hit(f"safe-{number}") for number in range(3)]
    hits.extend(
        [
            make_hit("wrong-audience", allowed_audiences=["caregiver"]),
            make_hit("wrong-purpose", allowed_purposes=["research"]),
        ]
    )

    response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(
        make_request(audience="elder", purpose="care_guidance")
    )

    assert response.status == "SUCCESS"
    assert {result.chunk_id for result in response.results} == {
        "safe-0",
        "safe-1",
        "safe-2",
    }


@pytest.mark.asyncio
async def test_successful_retrieval_contains_complete_citations() -> None:
    hits = [make_hit(f"chunk-{number}", score=5.0 - number) for number in range(5)]

    response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(make_request())

    assert response.status == "SUCCESS"
    assert len(response.results) == 5
    first = response.results[0]
    assert first.document_name == "合成長照指引"
    assert first.section == "申請流程"
    assert (first.page_start, first.page_end) == (10, 11)
    assert first.source_url == "https://example.test/guide"
    cited_context = render_cited_chunk(first)
    assert "來源：[合成長照指引，申請流程，pp. 10–11]" in cited_context
    assert first.source_url in cited_context


@pytest.mark.asyncio
async def test_incomplete_citation_metadata_is_not_exposed_to_agent() -> None:
    hits = [make_hit(f"safe-{number}") for number in range(2)]
    incomplete = make_hit("missing-source")
    incomplete["_source"]["source_url"] = None
    hits.append(incomplete)

    response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(make_request())

    assert response.status == "NO_DATA"
    assert response.results == []
    assert "不足三筆" in response.fallback_message
