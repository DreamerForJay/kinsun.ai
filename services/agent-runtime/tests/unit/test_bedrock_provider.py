from __future__ import annotations

from typing import Any

import pytest

from agent_runtime.contracts.models import AgentRunRequest, ContextItem, ContextManifest
from agent_runtime.models.bedrock_provider import (
    COMPANION_SYSTEM_PROMPT,
    KNOWLEDGE_SYSTEM_PROMPT,
    BedrockModelProvider,
    ModelDependencyError,
)

ELDER_ID = "2a6f9c31-8e47-4b52-9d10-3c8a7e5b1a40"
TENANT_ID = "6f1d2c44-9b3e-4a71-8c25-1de4f7a90b33"


class FakeConverseClient:
    def __init__(self, reply: str = "節錄提到家庭照顧者的定義。") -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": self.reply}]}}}


class ExplodingConverseClient:
    def converse(self, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("upstream detail naming the elder's words")


def make_request(text: str = "家庭照顧者是什麼意思？") -> AgentRunRequest:
    return AgentRunRequest(
        schema_version="1.0.0",
        request_id="req-bedrock-001",
        trace_id="trace-bedrock-001",
        session_id="sess-bedrock-001",
        actor_id="actor-elder-001",
        actor_role="elder",
        elder_id=ELDER_ID,
        tenant_id=TENANT_ID,
        purpose="legal_reference",
        consent_version="cv-2026.07.30",
        policy_version="pv-2026.07.30",
        language="zh-TW",
        input_text=text,
        allowed_tools=[],
        max_steps=3,
        latency_budget_ms=3000,
    )


def make_manifest(*, with_excerpts: bool) -> ContextManifest:
    items = [
        ContextItem(
            item_id="ctx-req-bedrock-001",
            source_type="user_input",
            content="家庭照顧者是什麼意思？",
            token_estimate=10,
        )
    ]
    if with_excerpts:
        items.append(
            ContextItem(
                item_id="rag-1-abc",
                source_type="rag-approved",
                content="知識庫節錄：家庭照顧者指於家庭中對失能者提供規律性照顧之主要親屬。",
                token_estimate=30,
            )
        )
    return ContextManifest(
        agent_id="companion",
        elder_id=ELDER_ID,
        tenant_id=TENANT_ID,
        purpose="legal_reference",
        consent_version="consent-v1",
        policy_version="policy-v1",
        items=items,
        excluded_items=[],
        total_token_estimate=sum(item.token_estimate for item in items),
    )


def make_provider(client: Any) -> BedrockModelProvider:
    return BedrockModelProvider(
        client,
        model_id="configured-model-id",
        max_tokens=512,
        temperature=0.2,
    )


@pytest.mark.asyncio
async def test_knowledge_turn_sends_only_the_approved_excerpts_as_grounding() -> None:
    client = FakeConverseClient()

    reply = await make_provider(client).generate_reply(
        make_request(), make_manifest(with_excerpts=True), "zh-TW"
    )

    assert reply == "節錄提到家庭照顧者的定義。"
    call = client.calls[0]
    assert call["modelId"] == "configured-model-id"
    system_text = call["system"][0]["text"]
    assert KNOWLEDGE_SYSTEM_PROMPT in system_text
    assert "zh-TW" in system_text
    user_text = call["messages"][0]["content"][0]["text"]
    assert "家庭照顧者指於家庭中對失能者提供規律性照顧之主要親屬" in user_text
    assert "只根據上面的節錄回答" in user_text


@pytest.mark.asyncio
async def test_turn_without_excerpts_uses_the_companion_prompt() -> None:
    client = FakeConverseClient(reply="謝謝您和我分享。")

    await make_provider(client).generate_reply(
        make_request("今天天氣真好"), make_manifest(with_excerpts=False), "zh-TW"
    )

    system_text = client.calls[0]["system"][0]["text"]
    assert COMPANION_SYSTEM_PROMPT in system_text
    assert KNOWLEDGE_SYSTEM_PROMPT not in system_text


@pytest.mark.asyncio
async def test_provider_failure_does_not_carry_the_upstream_message() -> None:
    """A provider message can quote the request, which is the elder speaking."""

    with pytest.raises(ModelDependencyError) as excinfo:
        await make_provider(ExplodingConverseClient()).generate_reply(
            make_request(), make_manifest(with_excerpts=True), "zh-TW"
        )

    assert "RuntimeError" in str(excinfo.value)
    assert "elder" not in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {},
        {"output": {}},
        {"output": {"message": {"content": []}}},
        {"output": {"message": {"content": [{"text": "   "}]}}},
    ],
)
async def test_unusable_response_fails_closed(response: dict[str, Any]) -> None:
    class Client:
        def converse(self, **kwargs: Any) -> dict[str, Any]:
            return response

    with pytest.raises(ModelDependencyError):
        await make_provider(Client()).generate_reply(
            make_request(), make_manifest(with_excerpts=True), "zh-TW"
        )


def test_construction_rejects_out_of_range_generation_settings() -> None:
    with pytest.raises(ValueError, match="temperature"):
        BedrockModelProvider(FakeConverseClient(), model_id="m", max_tokens=512, temperature=1.5)
    with pytest.raises(ValueError, match="max_tokens"):
        BedrockModelProvider(FakeConverseClient(), model_id="m", max_tokens=0, temperature=0.2)
