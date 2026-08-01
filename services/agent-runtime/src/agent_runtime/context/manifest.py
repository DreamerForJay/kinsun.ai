from collections.abc import Sequence

from agent_runtime.contracts.models import AgentRunRequest, ContextItem, ContextManifest


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 2)


def build_context_items(request: AgentRunRequest) -> list[ContextItem]:
    return [
        ContextItem(
            item_id=f"ctx-{request.request_id}",
            source_type="user_input",
            content=request.input_text,
            token_estimate=estimate_tokens(request.input_text),
        )
    ]


def build_context_manifest(
    request: AgentRunRequest,
    agent_id: str,
    *,
    item_limit: int = 1,
    additional_items: Sequence[ContextItem] = (),
) -> ContextManifest:
    items = [*build_context_items(request)[:item_limit], *additional_items]
    total = sum(item.token_estimate for item in items)
    return ContextManifest(
        agent_id=agent_id,
        elder_id=request.elder_id,
        tenant_id=request.tenant_id,
        purpose=request.purpose,
        consent_version=request.consent_version,
        policy_version=request.policy_version,
        items=items,
        excluded_items=[],
        total_token_estimate=total,
    )
