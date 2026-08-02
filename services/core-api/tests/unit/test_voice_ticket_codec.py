"""Security-focused tests for opaque, one-time Voice Ticket capabilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.core.exceptions import AuthenticationError
from app.services.voice_ticket_codec import VoiceTicketCodec

NOW = datetime(2026, 8, 2, 9, 0, tzinfo=UTC)
SECRET = "unit-test-voice-ticket-secret-material-32-bytes"


def _conversation(**overrides):
    values = {
        "id": UUID("51000000-0000-4000-8000-000000000001"),
        "initiator_actor_id": UUID("20000000-0000-4000-8000-000000000001"),
        "tenant_id": UUID("10000000-0000-4000-8000-000000000001"),
        "elder_id": UUID("40000000-0000-4000-8000-000000000001"),
        "consent_id": UUID("81000000-0000-4000-8000-000000000001"),
        "consent_version": 1,
        "started_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_ticket_is_stable_opaque_and_bound_to_secret() -> None:
    conversation = _conversation()
    first = VoiceTicketCodec(SECRET, now=lambda: NOW).issue(conversation)
    replay = VoiceTicketCodec(SECRET, now=lambda: NOW).issue(conversation)
    other_secret = VoiceTicketCodec(
        "different-unit-test-voice-secret-material-32-bytes",
        now=lambda: NOW,
    ).issue(conversation)

    assert first == replay
    assert first.value != other_secret.value
    assert len(first.value) == 43
    assert str(conversation.id) not in first.value
    assert str(conversation.tenant_id) not in first.value
    assert str(conversation.elder_id) not in first.value
    assert first.expires_at == NOW + timedelta(seconds=60)


def test_ticket_verifies_only_for_exact_server_owned_scope() -> None:
    codec = VoiceTicketCodec(SECRET, now=lambda: NOW + timedelta(seconds=10))
    ticket = codec.issue(_conversation()).value

    codec.verify(ticket, _conversation())
    with pytest.raises(AuthenticationError, match="invalid or unavailable"):
        codec.verify(
            ticket,
            _conversation(elder_id=UUID("40000000-0000-4000-8000-000000000002")),
        )


def test_expired_or_tampered_ticket_fails_with_same_safe_error() -> None:
    ticket = VoiceTicketCodec(SECRET, now=lambda: NOW).issue(_conversation()).value
    expired = VoiceTicketCodec(SECRET, now=lambda: NOW + timedelta(seconds=60))
    current = VoiceTicketCodec(SECRET, now=lambda: NOW + timedelta(seconds=1))

    for value, codec in ((ticket, expired), (f"{ticket[:-1]}x", current), ("bad", current)):
        with pytest.raises(AuthenticationError) as exc_info:
            codec.verify(value, _conversation())
        assert str(exc_info.value) == "Voice ticket is invalid or unavailable"
        assert value not in str(exc_info.value)


def test_ticket_requires_actor_binding_and_strong_configuration() -> None:
    codec = VoiceTicketCodec(SECRET, now=lambda: NOW)

    with pytest.raises(AuthenticationError):
        codec.issue(_conversation(initiator_actor_id=None))
    with pytest.raises(ValueError, match="at least 32 bytes"):
        VoiceTicketCodec("too-short")
    with pytest.raises(ValueError, match="between 15 and 120"):
        VoiceTicketCodec(SECRET, ttl_seconds=121)
