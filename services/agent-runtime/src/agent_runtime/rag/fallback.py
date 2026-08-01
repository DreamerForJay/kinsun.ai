from __future__ import annotations

from agent_runtime.rag.models import RetrievalResponseV1

NO_DATA_MESSAGE = (
    "目前找不到符合篩選條件且可靠引用的資料，因此無法根據知識庫回答；"
    "請查閱官方來源或詢問專業人員。"
)
INSUFFICIENT_DATA_MESSAGE = "目前可靠來源不足三筆，為避免根據不足資料推測，本次不產生知識庫回答。"
UNAVAILABLE_MESSAGE = "知識庫目前無法取用，為避免猜測，本次不產生知識庫回答。"


def no_data_response(request_id: str, *, insufficient: bool = False) -> RetrievalResponseV1:
    message = INSUFFICIENT_DATA_MESSAGE if insufficient else NO_DATA_MESSAGE
    return RetrievalResponseV1(
        schema_version="1.0.0",
        request_id=request_id,
        status="NO_DATA",
        fallback_message=message,
        results=[],
    )


def failed_response(request_id: str) -> RetrievalResponseV1:
    return RetrievalResponseV1(
        schema_version="1.0.0",
        request_id=request_id,
        status="FAILED",
        fallback_message=UNAVAILABLE_MESSAGE,
        results=[],
    )
