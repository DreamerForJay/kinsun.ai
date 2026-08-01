"""Opaque, human-readable invitation codes with hash-only persistence."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from app.core.exceptions import ValidationError

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 16  # 80 bits from a 32-character alphabet.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class FamilyInvitationTokenCodec:
    """Generate invitation codes and compute domain-separated HMACs."""

    def __init__(self, secret: str) -> None:
        if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
            raise ValueError("Family invitation HMAC secret must contain at least 32 bytes")
        self._secret = secret.encode("utf-8")

    @staticmethod
    def normalize_code(value: str) -> str:
        normalized = "".join(character for character in value.upper() if character.isalnum())
        if len(normalized) != _CODE_LENGTH or any(
            character not in _ALPHABET for character in normalized
        ):
            raise ValidationError(
                details=[
                    {
                        "field": "invitation_code",
                        "reason": "Invitation code is unavailable",
                    }
                ]
            )
        return normalized

    @staticmethod
    def display_code(normalized: str) -> str:
        return "-".join(normalized[index : index + 4] for index in range(0, len(normalized), 4))

    @staticmethod
    def normalize_email(value: str) -> str:
        normalized = value.strip().casefold()
        if len(normalized) > 254 or not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValidationError(
                details=[{"field": "invitee_email", "reason": "Email format is invalid"}]
            )
        return normalized

    def generate(self) -> tuple[str, str]:
        normalized = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
        return self.display_code(normalized), self.hash_code(normalized)

    def hash_code(self, value: str) -> str:
        normalized = self.normalize_code(value)
        return self._hmac("invite", normalized)

    def hash_email(self, value: str) -> str:
        return self._hmac("email", self.normalize_email(value))

    @staticmethod
    def matches(expected: str, actual: str) -> bool:
        return hmac.compare_digest(expected, actual)

    def _hmac(self, purpose: str, value: str) -> str:
        return hmac.new(
            self._secret,
            f"{purpose}:{value}".encode(),
            hashlib.sha256,
        ).hexdigest()
