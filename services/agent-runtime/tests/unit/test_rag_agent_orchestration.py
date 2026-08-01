import pytest

from agent_runtime.common.enums import ResultStatus
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest
from agent_runtime.models.provider import ModelProvider
from agent_runtime.orchestration.orchestrator import AgentOrchestrator
from agent_runtime.rag.fallback import failed_response, no_data_response
from agent_runtime.rag.models import (
    RetrievalRequestV1,
    RetrievalResponseV1,
    RetrievalResultV1,
)


class CapturingProvider(ModelProvider):
    def __init__(self, reply: str = "以下是根據知識庫整理的資訊。") -> None:
        self.reply = reply
        self.context_manifest: ContextManifest | None = None
        self.call_count = 0

    async def generate_reply(
        self,
        request: AgentRunRequest,
        context_manifest: ContextManifest,
        language: str,
    ) -> str:
        self.call_count += 1
        self.context_manifest = context_manifest
        return self.reply


class StubRetriever:
    def __init__(self, response: RetrievalResponseV1) -> None:
        self.response = response
        self.requests: list[RetrievalRequestV1] = []

    async def retrieve(self, request: RetrievalRequestV1) -> RetrievalResponseV1:
        self.requests.append(request)
        return self.response


class UnexpectedRetriever:
    async def retrieve(self, request: RetrievalRequestV1) -> RetrievalResponseV1:
        raise AssertionError(f"RAG should not be called for purpose {request.purpose}")


def make_request(**overrides: object) -> AgentRunRequest:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "request_id": "req-rag-agent-001",
        "trace_id": "trace-rag-agent-001",
        "session_id": "sess-rag-agent-001",
        "actor_id": "actor-elder-001",
        "actor_role": "elder",
        "elder_id": "elder-001",
        "tenant_id": "tenant-001",
        "purpose": "general_information",
        "consent_version": "cv-synthetic-001",
        "policy_version": "pv-synthetic-001",
        "language": "zh-TW",
        "input_text": "長照服務的申請流程是什麼？",
        "allowed_tools": [],
        "max_steps": 3,
        "latency_budget_ms": 3000,
    }
    values.update(overrides)
    return AgentRunRequest.model_validate(values)


def make_result(position: int, *, text: str | None = None) -> RetrievalResultV1:
    return RetrievalResultV1(
        chunk_id=f"SYNTHETIC-CHUNK-{position:03d}",
        text=text or f"這是第 {position} 筆合成的長照申請資訊。",
        score=0.9 - position / 100,
        document_name=f"合成長照指引 {position}",
        section="申請流程",
        page_start=position,
        page_end=position + 1,
        source_url=f"https://example.invalid/long-term-care/{position}",
    )


def success_response(request_id: str, count: int = 4) -> RetrievalResponseV1:
    return RetrievalResponseV1(
        schema_version="1.0.0",
        request_id=request_id,
        status="SUCCESS",
        fallback_message=None,
        results=[make_result(position) for position in range(1, count + 1)],
    )


@pytest.mark.asyncio
async def test_successful_rag_chunks_reach_agent_context_and_reply_cites_every_source():
    request = make_request()
    provider = CapturingProvider()
    retriever = StubRetriever(success_response(request.request_id))
    orchestrator = AgentOrchestrator(provider, max_steps=3)

    response = await orchestrator.run(request, rag_retriever=retriever)

    assert provider.call_count == 1
    assert len(retriever.requests) == 1
    retrieval_request = retriever.requests[0]
    assert retrieval_request.query == request.input_text
    assert retrieval_request.query_profile == "natural_language"
    assert retrieval_request.top_k == 5
    assert retrieval_request.audience == "elder"
    assert retrieval_request.purpose == "general_information"

    assert provider.context_manifest is not None
    rag_items = [
        item for item in provider.context_manifest.items if item.source_type == "rag-approved"
    ]
    assert len(rag_items) == 4
    for position, item in enumerate(rag_items, start=1):
        assert len(item.content) <= 2048
        assert "僅作資料依據" in item.content
        assert f"SYNTHETIC-CHUNK-{position:03d}" in item.content
        assert f"https://example.invalid/long-term-care/{position}" in item.content

    assert response.result_status == ResultStatus.SUCCESS
    assert "引用來源：" in response.reply_text
    for position in range(1, 5):
        assert f"合成長照指引 {position}" in response.reply_text
        assert f"https://example.invalid/long-term-care/{position}" in response.reply_text


@pytest.mark.asyncio
@pytest.mark.parametrize("retrieval_status", ["NO_DATA", "FAILED"])
async def test_no_data_or_failed_rag_never_calls_agent_or_guesses(retrieval_status: str):
    request = make_request()
    provider = CapturingProvider(reply="這段不應出現在回覆中。")
    retrieval = (
        no_data_response(request.request_id)
        if retrieval_status == "NO_DATA"
        else failed_response(request.request_id)
    )
    orchestrator = AgentOrchestrator(provider, max_steps=3)

    response = await orchestrator.run(
        request,
        rag_retriever=StubRetriever(retrieval),
    )

    assert provider.call_count == 0
    assert response.result_status == ResultStatus.SAFE_FALLBACK
    assert response.reason_codes == [f"RAG_{retrieval_status}"]
    assert response.reply_text == retrieval.fallback_message
    assert "這段不應出現在回覆中" not in response.reply_text


@pytest.mark.asyncio
async def test_missing_rag_adapter_fails_closed_for_explicit_knowledge_request():
    request = make_request()
    provider = CapturingProvider(reply="這段不應出現在回覆中。")
    orchestrator = AgentOrchestrator(provider, max_steps=3)

    response = await orchestrator.run(request, rag_retriever=None)

    assert provider.call_count == 0
    assert response.result_status == ResultStatus.SAFE_FALLBACK
    assert response.reason_codes == ["RAG_FAILED"]
    assert "無法取用" in response.reply_text


@pytest.mark.asyncio
async def test_mismatched_retrieval_request_id_fails_closed():
    request = make_request()
    provider = CapturingProvider(reply="這段不應出現在回覆中。")
    mismatched = success_response("req-another-turn")
    orchestrator = AgentOrchestrator(provider, max_steps=3)

    response = await orchestrator.run(
        request,
        rag_retriever=StubRetriever(mismatched),
    )

    assert provider.call_count == 0
    assert response.result_status == ResultStatus.SAFE_FALLBACK
    assert response.reason_codes == ["RAG_FAILED"]


@pytest.mark.asyncio
async def test_conversation_purpose_does_not_trigger_rag():
    request = make_request(purpose="conversation", input_text="我今天早餐吃了粥。")
    provider = CapturingProvider(reply="謝謝您和我分享。")
    orchestrator = AgentOrchestrator(provider, max_steps=3)

    response = await orchestrator.run(request, rag_retriever=UnexpectedRetriever())

    assert provider.call_count == 1
    assert response.result_status == ResultStatus.SUCCESS
    assert response.reply_text == "謝謝您和我分享。"
    assert "引用來源" not in response.reply_text


@pytest.mark.asyncio
async def test_high_risk_request_is_not_sent_to_rag():
    request = make_request(input_text="請告訴我怎麼停藥")
    provider = CapturingProvider(reply="一般回覆")
    orchestrator = AgentOrchestrator(provider, max_steps=3)

    response = await orchestrator.run(request, rag_retriever=UnexpectedRetriever())

    assert response.result_status == ResultStatus.BLOCKED
    assert "醫療建議" in response.reply_text
    assert "引用來源" not in response.reply_text
