"""Opaque, short-lived Voice Ticket capabilities.

Tickets intentionally contain no decodable actor, tenant, elder, consent, or
session data. The caller supplies the session ID separately; Core reloads the
server-owned conversation row and recomputes the expected HMAC capability.
Single-use consumption is enforced by locking that row and allowing only the
CREATED -> RECORDING transition.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, ServiceUnavailableError

if TYPE_CHECKING:
    from app.models.conversation import ConversationSession

_INVALID_TICKET_MESSAGE = "Voice ticket is invalid or unavailable"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class IssuedVoiceTicket:
    """Opaque capability and its public expiry metadata."""

    value: str
    expires_at: datetime


class VoiceTicketCodec:
    """Issue and verify deterministic, server-bound HMAC capabilities."""

    def __init__(
        self,
        secret: str,
        ttl_seconds: int = 60,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("Voice Ticket secret must contain at least 32 bytes")
        if not 15 <= ttl_seconds <= 120:
            raise ValueError("Voice Ticket TTL must be between 15 and 120 seconds")
        self._secret = secret.encode("utf-8")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._now = now

    def issue(self, conversation: ConversationSession) -> IssuedVoiceTicket:
        """Return the stable capability for one server-owned conversation row."""
        started_at = self._started_at(conversation)
        return IssuedVoiceTicket(
            value=self._expected_value(conversation, started_at),
            expires_at=started_at + self._ttl,
        )

    def verify(self, value: str, conversation: ConversationSession) -> None:
        """Fail closed without disclosing which ticket binding was invalid."""
        try:
            started_at = self._started_at(conversation)
            expires_at = started_at + self._ttl
            expected = self._expected_value(conversation, started_at)
            valid_shape = 32 <= len(value) <= 128 and value.isascii()
            if (
                not valid_shape
                or self._now() >= expires_at
                or not hmac.compare_digest(value, expected)
            ):
                raise AuthenticationError(_INVALID_TICKET_MESSAGE)
        except AuthenticationError:
            raise
        except Exception:
            raise AuthenticationError(_INVALID_TICKET_MESSAGE) from None

    def _expected_value(
        self,
        conversation: ConversationSession,
        started_at: datetime,
    ) -> str:
        actor_id = conversation.initiator_actor_id
        if actor_id is None:
            raise AuthenticationError(_INVALID_TICKET_MESSAGE)
        nonce = hmac.new(
            self._secret,
            f"kinsun.voice-ticket.nonce.v1:{conversation.id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        claims = {
            "actor_id": str(actor_id),
            "audience": "kinsun-speech-gateway",
            "consent_id": str(conversation.consent_id),
            "consent_version": conversation.consent_version,
            "elder_id": str(conversation.elder_id),
            "expires_at": int((started_at + self._ttl).timestamp()),
            "issued_at": int(started_at.timestamp()),
            "issuer": "kinsun-core-api",
            "nonce": nonce,
            "purpose": "BASIC_VOICE",
            "session_id": str(conversation.id),
            "tenant_id": str(conversation.tenant_id),
            "version": 1,
        }
        canonical = json.dumps(
            claims,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hmac.new(self._secret, canonical, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    @staticmethod
    def _started_at(conversation: ConversationSession) -> datetime:
        started_at = conversation.started_at
        if started_at is None:
            raise AuthenticationError(_INVALID_TICKET_MESSAGE)
        if started_at.tzinfo is None:
            return started_at.replace(tzinfo=UTC)
        return started_at.astimezone(UTC)


def get_voice_ticket_codec() -> VoiceTicketCodec:
    """Build the configured codec or fail before any session side effect."""
    settings = get_settings()
    if not settings.voice_ticket_enabled:
        raise ServiceUnavailableError("Voice Ticket issuance is not configured")
    try:
        return VoiceTicketCodec(
            settings.voice_ticket_hmac_secret,
            settings.voice_ticket_ttl_seconds,
        )
    except ValueError:
        raise ServiceUnavailableError("Voice Ticket issuance is not configured") from None
