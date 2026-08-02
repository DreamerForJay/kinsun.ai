"""ASR evidence must bind the exact text passed to Agent Runtime."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import AuthenticationError
from app.services.asr_gate_service import AsrGateService


def _service_and_conversation():
    tenant_id = uuid4()
    conversation = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        state="PROCESSING",
        consent_id=uuid4(),
        consent_version=1,
    )
    service = AsrGateService(
        MagicMock(),
        tenant_id,
        digest_secret="synthetic-asr-gate-secret-at-least-32-bytes",
        confidence_threshold=0.85,
        evidence_ttl_seconds=900,
    )
    service._require_live_voice_consent = AsyncMock()
    return service, conversation


@pytest.mark.asyncio
async def test_digest_mismatch_is_rejected() -> None:
    service, conversation = _service_and_conversation()
    evidence = SimpleNamespace(
        elder_id=conversation.elder_id,
        gate_status="ALLOWED",
        confirmation_action=None,
        transcript_digest=service._digest("原本通過 Gate 的合成文字"),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    service._repo = SimpleNamespace(get_for_session_for_update=AsyncMock(return_value=evidence))

    with pytest.raises(AuthenticationError, match="ASR input is unavailable"):
        await service.authorize_agent_input(
            conversation=conversation,
            input_text="被替換的另一段合成文字",
        )


@pytest.mark.asyncio
async def test_unconfirmed_evidence_is_rejected() -> None:
    service, conversation = _service_and_conversation()
    input_text = "尚未由長者確認的合成文字"
    evidence = SimpleNamespace(
        elder_id=conversation.elder_id,
        gate_status="AWAITING_CONFIRMATION",
        confirmation_action=None,
        transcript_digest=service._digest(input_text),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    service._repo = SimpleNamespace(get_for_session_for_update=AsyncMock(return_value=evidence))

    with pytest.raises(AuthenticationError, match="ASR input is unavailable"):
        await service.authorize_agent_input(
            conversation=conversation,
            input_text=input_text,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("gate_status", "confirmation_action"),
    [("ALLOWED", None), ("CONFIRMED", "CONFIRM")],
)
async def test_allowed_or_confirmed_matching_evidence_is_accepted(
    gate_status: str,
    confirmation_action: str | None,
) -> None:
    service, conversation = _service_and_conversation()
    input_text = "已通過 ASR Gate 的合成文字"
    evidence = SimpleNamespace(
        elder_id=conversation.elder_id,
        gate_status=gate_status,
        confirmation_action=confirmation_action,
        transcript_digest=service._digest(input_text),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    service._repo = SimpleNamespace(get_for_session_for_update=AsyncMock(return_value=evidence))

    await service.authorize_agent_input(
        conversation=conversation,
        input_text=input_text,
    )
