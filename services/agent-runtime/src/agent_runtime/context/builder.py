from collections.abc import Sequence
from hashlib import sha256

from agent_runtime.context.manifest import build_context_manifest
from agent_runtime.contracts.models import AgentRunRequest, ContextItem, ContextManifest
from agent_runtime.rag.citations import render_controlled_cited_chunk
from agent_runtime.rag.models import RetrievalResultV1


def build_minimal_context_manifest(request: AgentRunRequest, agent_id: str) -> ContextManifest:
    return build_context_manifest(request, agent_id)


def build_rag_context_manifest(
    request: AgentRunRequest,
    agent_id: str,
    results: Sequence[RetrievalResultV1],
) -> ContextManifest:
    """Add only a complete, bounded 3–5 chunk retrieval result to Agent context."""

    if not 3 <= len(results) <= 5:
        raise ValueError("RAG context requires three to five validated chunks")
    rag_items = [
        _build_rag_context_item(result, position)
        for position, result in enumerate(results, start=1)
    ]
    return build_context_manifest(
        request,
        agent_id,
        additional_items=rag_items,
    )


def _rag_context_item_id(chunk_id: str, position: int) -> str:
    digest = sha256(chunk_id.encode("utf-8")).hexdigest()[:16]
    return f"rag-{position}-{digest}"


def _build_rag_context_item(result: RetrievalResultV1, position: int) -> ContextItem:
    content = render_controlled_cited_chunk(result)
    return ContextItem(
        item_id=_rag_context_item_id(result.chunk_id, position),
        source_type="rag-approved",
        content=content,
        token_estimate=_estimate_context_tokens(content),
    )


def _estimate_context_tokens(text: str) -> int:
    return max(1, len(text) // 2)
