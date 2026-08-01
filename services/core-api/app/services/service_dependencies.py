"""Small, cache-safe service dependencies assembled from validated settings."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec


@lru_cache(maxsize=4)
def _build_family_invitation_token_codec(secret: str) -> FamilyInvitationTokenCodec:
    return FamilyInvitationTokenCodec(secret)


def get_family_invitation_token_codec() -> FamilyInvitationTokenCodec:
    secret = get_settings().family_invitation_hmac_secret
    try:
        return _build_family_invitation_token_codec(secret)
    except ValueError as exc:
        raise ServiceUnavailableError("Family invitation service is unavailable") from exc
