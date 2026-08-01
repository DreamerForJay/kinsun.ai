"""Security-focused tests for the family invitation token codec."""

from __future__ import annotations

import re

import pytest

from app.core.exceptions import ValidationError
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec


@pytest.fixture
def codec() -> FamilyInvitationTokenCodec:
    return FamilyInvitationTokenCodec("unit-test-family-invitation-secret-32-bytes")


def test_generate_returns_grouped_code_and_hash_only_digest(
    codec: FamilyInvitationTokenCodec,
) -> None:
    display_code, token_hash = codec.generate()

    assert re.fullmatch(r"[A-HJ-NP-Z2-9]{4}(?:-[A-HJ-NP-Z2-9]{4}){3}", display_code)
    assert re.fullmatch(r"[0-9a-f]{64}", token_hash)
    assert token_hash == codec.hash_code(display_code)
    assert display_code.replace("-", "") not in token_hash


def test_hash_code_is_format_insensitive_but_secret_bound() -> None:
    first = FamilyInvitationTokenCodec("first-unit-test-secret-material-32-bytes")
    second = FamilyInvitationTokenCodec("second-unit-test-secret-material-32-bytes")
    normalized = "ABCD2345EFGH6789"

    assert first.hash_code(normalized) == first.hash_code("abcd-2345-efgh-6789")
    assert first.hash_code(normalized) != second.hash_code(normalized)


@pytest.mark.parametrize(
    "invalid_code",
    ["", "ABCD-EFGH-IJKL", "ABCD-EFGH-IJKL-MNO0", "ABCD EFGH IJKL MNO1"],
)
def test_invalid_code_fails_closed(
    codec: FamilyInvitationTokenCodec,
    invalid_code: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        codec.hash_code(invalid_code)

    assert exc_info.value.details == [
        {"field": "invitation_code", "reason": "Invitation code is unavailable"}
    ]


def test_email_hash_normalizes_case_without_persisting_email(
    codec: FamilyInvitationTokenCodec,
) -> None:
    digest = codec.hash_email("  Family.Member@Example.COM ")

    assert digest == codec.hash_email("family.member@example.com")
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert "family.member" not in digest


@pytest.mark.parametrize("email", ["", "missing-at.example.com", "a@b", "a b@example.com"])
def test_invalid_email_is_rejected(codec: FamilyInvitationTokenCodec, email: str) -> None:
    with pytest.raises(ValidationError):
        codec.hash_email(email)


def test_short_hmac_secret_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        FamilyInvitationTokenCodec("too-short")
