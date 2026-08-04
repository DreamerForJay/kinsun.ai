"""Fail-closed confirmation authority tests for long-term memory."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationDeniedError, ValidationError
from app.middleware.auth import ActorContext
from app.services.consent_service import ConsentService
from app.services.memory_service import MemoryService


def actor(role: str) -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role=role,
        tenant_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_voice_confirmation_is_rejected_before_any_repository_access() -> None:
    session = MagicMock()
    service = MemoryService(session, uuid4())

    with pytest.raises(ValidationError) as exc_info:
        await service._validate_confirmation_authority(
            memory=SimpleNamespace(elder_id=uuid4()),
            actor_context=actor("ELDER"),
            request=SimpleNamespace(confirmation_method="VOICE"),
        )

    assert exc_info.value.details[0]["field"] == "confirmation_method"
    session.scalar.assert_not_called()
    session.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "method"),
    [
        ("DAYCARE_CARE_WORKER", "CAREGIVER_REVIEW"),
        ("HOME_CARE_WORKER", "CAREGIVER_REVIEW"),
        ("FAMILY_MEMBER", "LEGAL_REPRESENTATIVE"),
    ],
)
async def test_non_elder_confirmation_fails_without_repository_access(
    role: str,
    method: str,
) -> None:
    session = MagicMock()
    service = MemoryService(session, uuid4())

    with pytest.raises(AuthorizationDeniedError, match="Resource not found"):
        await service._validate_confirmation_authority(
            memory=SimpleNamespace(elder_id=uuid4()),
            actor_context=actor(role),
            request=SimpleNamespace(confirmation_method=method),
        )

    session.scalar.assert_not_called()
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_elder_ui_confirmation_activates_with_server_generated_evidence() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    service = MemoryService(session, uuid4())
    service._write_event = AsyncMock()
    elder = actor("ELDER")
    memory = SimpleNamespace(
        elder_id=uuid4(),
        current_version=2,
        consent_version=3,
        status="CANDIDATE",
        confirmed_by_actor_id=None,
        confirmed_at=None,
        confirmation_method=None,
        confirmation_session_id=None,
        confirmation_evidence_ref=None,
        activated_at=None,
    )
    request = SimpleNamespace(
        confirmation_method="ELDER_UI",
        expected_candidate_version=2,
        consent_version=3,
    )

    with patch.object(
        ConsentService,
        "require_active",
        AsyncMock(return_value=SimpleNamespace(version=3)),
    ):
        result = await service.confirm(
            memory=memory,
            actor_context=elder,
            request=request,
            trace_id="trace-synthetic-elder-confirmation",
            idempotency_key="idem-synthetic-elder-confirmation",
        )

    assert result.status == "ACTIVE"
    assert result.confirmed_by_actor_id == elder.actor_id
    assert result.confirmation_method == "ELDER_UI"
    assert result.confirmation_session_id is None
    assert result.confirmation_evidence_ref == "core-command:trace-synthetic-elder-confirmation"
    session.flush.assert_awaited_once()
    service._write_event.assert_awaited_once()
