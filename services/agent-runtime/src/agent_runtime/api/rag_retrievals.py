"""Fail-closed HTTP boundary for staging knowledge retrieval."""

from fastapi import APIRouter, Request

from agent_runtime.core.envelopes import ResponseMeta, SuccessEnvelope
from agent_runtime.middleware.correlation import get_correlation_id
from agent_runtime.rag.fallback import failed_response
from agent_runtime.rag.models import RetrievalRequestV1, RetrievalResponseV1

router = APIRouter(tags=["rag"])


@router.post(
    "/api/v1/rag/retrievals",
    response_model=SuccessEnvelope[RetrievalResponseV1],
)
async def retrieve_knowledge(
    request: Request,
    payload: RetrievalRequestV1,
) -> SuccessEnvelope[RetrievalResponseV1]:
    """Retrieve approved staging chunks or return an explicit no-guess fallback.

    A missing provider configuration is a knowledge outcome rather than an
    invitation for the Agent to improvise. Provider failures are similarly
    converted by ``Retriever`` into a ``FAILED`` response with no partial
    chunks.
    """

    retriever = getattr(request.app.state, "rag_retriever", None)
    result = (
        failed_response(payload.request_id)
        if retriever is None
        else await retriever.retrieve(payload)
    )
    return SuccessEnvelope(
        data=result,
        meta=ResponseMeta(correlation_id=get_correlation_id()),
    )
