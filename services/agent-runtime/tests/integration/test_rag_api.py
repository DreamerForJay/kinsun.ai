from __future__ import annotations

from httpx import ASGITransport, AsyncClient

import agent_runtime.app as app_module
from agent_runtime.app import _resolve_config_path, create_app
from agent_runtime.rag.models import RetrievalResponseV1, RetrievalResultV1

RAG_PATH = "/api/v1/rag/retrievals"


def request_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "request_id": "req-rag-001",
        "query": "居家服務的申請條件是什麼？",
        "query_profile": "natural_language",
        "top_k": 5,
        "language": "zh-TW",
    }
    payload.update(overrides)
    return payload


async def post(app, payload: dict[str, object]):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(RAG_PATH, json=payload)


async def test_unconfigured_retrieval_returns_explicit_failed_fallback_without_guessing():
    app = create_app()
    query = "不可回填到錯誤訊息的測試查詢"
    response = await post(app, request_payload(query=query))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["data"]["status"] == "FAILED"
    assert body["data"]["results"] == []
    assert "不產生知識庫回答" in body["data"]["fallback_message"]
    assert query not in response.text


class StubRetriever:
    async def retrieve(self, payload) -> RetrievalResponseV1:
        results = [
            RetrievalResultV1(
                chunk_id=f"chunk-{number}",
                text=f"合成測試資料 {number}",
                score=1.0 - number / 10,
                document_name="長照測試文件",
                section="申請程序",
                page_start=number,
                page_end=number,
                source_url=f"https://example.test/source#{number}",
            )
            for number in range(1, 4)
        ]
        return RetrievalResponseV1(
            schema_version="1.0.0",
            request_id=payload.request_id,
            status="SUCCESS",
            fallback_message=None,
            results=results,
        )


async def test_retrieval_success_returns_three_cited_chunks_in_standard_envelope():
    app = create_app()
    app.state.rag_retriever = StubRetriever()
    response = await post(app, request_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "SUCCESS"
    assert len(body["data"]["results"]) == 3
    assert all(result["source_url"] for result in body["data"]["results"])
    assert body["meta"]["schema_version"] == "1.0"


async def test_retrieval_request_rejects_wrong_top_k_and_extra_fields():
    app = create_app()
    response = await post(app, request_payload(top_k=10, caller_dsl={"match_all": {}}))

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["reason_code"] == "REQUEST_VALIDATION_FAILED"


def test_repo_relative_rag_config_paths_work_from_service_directory(
    monkeypatch,
) -> None:
    service_directory = _resolve_config_path("services/agent-runtime/pyproject.toml").parent
    monkeypatch.chdir(service_directory)

    resolved = _resolve_config_path("config/rag/embedding.yaml")

    assert resolved.is_file()
    assert resolved.name == "embedding.yaml"


def test_runtime_factory_passes_settings_provider_values_to_rag_loader(monkeypatch) -> None:
    class StubSettings:
        RAG_MODE = "staging"
        RAG_EMBEDDING_CONFIG_PATH = "config/rag/embedding.yaml"
        RAG_OPENSEARCH_INDEX_CONFIG_PATH = "config/rag/opensearch-index-v1.json"
        RAG_HYBRID_NATURAL_CONFIG_PATH = "config/rag/hybrid-natural-language.json"
        RAG_HYBRID_LEGAL_CONFIG_PATH = "config/rag/hybrid-legal.json"
        AWS_REGION = "configured-region"
        BEDROCK_EMBEDDING_MODEL_ID = "configured-model"
        BEDROCK_EMBEDDING_DIMENSION = 1024
        OPENSEARCH_HOST = "https://search.example.test"
        OPENSEARCH_INDEX = "configured-staging-index"
        OPENSEARCH_ALIAS = "configured-staging-alias"

    captured = {}
    sentinel_settings = object()
    sentinel_retriever = object()

    def fake_loader(**kwargs):
        captured.update(kwargs)
        return sentinel_settings

    monkeypatch.setattr(app_module, "get_settings", lambda: StubSettings())
    monkeypatch.setattr(
        app_module.RagRuntimeSettings,
        "from_config_files",
        classmethod(lambda cls, **kwargs: fake_loader(**kwargs)),
    )
    monkeypatch.setattr(
        app_module,
        "build_retriever",
        lambda settings: sentinel_retriever if settings is sentinel_settings else None,
    )

    result = app_module.build_configured_rag_retriever()

    assert result is sentinel_retriever
    assert captured["environ"] == {
        "AWS_REGION": "configured-region",
        "BEDROCK_EMBEDDING_MODEL_ID": "configured-model",
        "BEDROCK_EMBEDDING_DIMENSION": "1024",
        "OPENSEARCH_HOST": "https://search.example.test",
        "OPENSEARCH_INDEX": "configured-staging-index",
        "OPENSEARCH_ALIAS": "configured-staging-alias",
        "RAG_MODE": "staging",
    }
