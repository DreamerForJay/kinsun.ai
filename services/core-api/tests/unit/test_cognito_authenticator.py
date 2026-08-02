"""Tests for the unbound Cognito authentication adapter boundary."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request

from app.adapters.auth.cognito import (
    CognitoActorContextResolver,
    CognitoAuthenticator,
    CognitoJwtVerifier,
    CognitoTokenVerifier,
    DatabaseCognitoActorContextResolver,
    VerifiedCognitoIdentity,
)
from app.core.exceptions import AuthenticationError
from app.middleware.auth import ActorContext


def _request(authorization: str | None) -> Request:
    headers = [] if authorization is None else [(b"authorization", authorization.encode())]
    return Request({"type": "http", "headers": headers})


class _StaticJwksCache:
    def __init__(self, key: dict) -> None:
        self._key = key
        self.calls: list[bool] = []

    async def get(self, kid: str, *, force_refresh: bool = False) -> dict:
        assert kid == "test-key"
        self.calls.append(force_refresh)
        return self._key


def _signed_token(*, claims: dict) -> tuple[str, _StaticJwksCache]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = "test-key"
    return (
        jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"}),
        _StaticJwksCache(jwk),
    )


def _verifier(cache: _StaticJwksCache) -> CognitoJwtVerifier:
    return CognitoJwtVerifier(
        region="ap-northeast-1",
        user_pool_id="ap-northeast-1_example",
        app_client_id="client-id",
        jwks_cache=cache,
    )


def _claims(**overrides: object) -> dict:
    claims: dict = {
        "iss": "https://cognito-idp.ap-northeast-1.amazonaws.com/ap-northeast-1_example",
        "sub": "cognito-subject",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "token_use": "access",
        "client_id": "client-id",
    }
    claims.update(overrides)
    return claims


async def test_cognito_authenticator_resolves_formal_actor_context() -> None:
    identity = VerifiedCognitoIdentity(subject="synthetic-subject")
    actor = ActorContext(
        actor_id=uuid4(),
        actor_role="DAYCARE_CARE_WORKER",
        tenant_id=uuid4(),
    )
    verifier = AsyncMock(spec=CognitoTokenVerifier)
    verifier.verify_access_token.return_value = identity
    resolver = AsyncMock(spec=CognitoActorContextResolver)
    resolver.resolve_actor_context.return_value = actor

    result = await CognitoAuthenticator(verifier, resolver).authenticate(
        _request("Bearer synthetic-token")
    )

    assert result == actor
    verifier.verify_access_token.assert_awaited_once_with("synthetic-token")
    resolver.resolve_actor_context.assert_awaited_once_with(identity)


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic synthetic-token", "Bearer", "Bearer token with spaces"],
)
async def test_cognito_authenticator_rejects_malformed_bearer_header(
    authorization: str | None,
) -> None:
    verifier = AsyncMock(spec=CognitoTokenVerifier)
    resolver = AsyncMock(spec=CognitoActorContextResolver)

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await CognitoAuthenticator(verifier, resolver).authenticate(_request(authorization))

    verifier.verify_access_token.assert_not_awaited()
    resolver.resolve_actor_context.assert_not_awaited()


async def test_cognito_authenticator_does_not_chain_provider_secret() -> None:
    verifier = AsyncMock(spec=CognitoTokenVerifier)
    verifier.verify_access_token.side_effect = RuntimeError("token=restricted-value")
    resolver = AsyncMock(spec=CognitoActorContextResolver)

    with pytest.raises(AuthenticationError) as exc_info:
        await CognitoAuthenticator(verifier, resolver).authenticate(
            _request("Bearer synthetic-token")
        )

    assert str(exc_info.value) == "Authentication required"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert "restricted-value" not in str(exc_info.value)
    resolver.resolve_actor_context.assert_not_awaited()


async def test_cognito_authenticator_rejects_untrusted_provider_types() -> None:
    verifier = AsyncMock(spec=CognitoTokenVerifier)
    verifier.verify_access_token.return_value = {"sub": "untrusted-claim"}
    resolver = AsyncMock(spec=CognitoActorContextResolver)

    with pytest.raises(AuthenticationError):
        await CognitoAuthenticator(verifier, resolver).authenticate(
            _request("Bearer synthetic-token")
        )

    resolver.resolve_actor_context.assert_not_awaited()


async def test_access_token_rs256_validation_returns_only_subject() -> None:
    token, cache = _signed_token(claims=_claims())

    identity = await _verifier(cache).verify_access_token(token)

    assert identity == VerifiedCognitoIdentity(subject="cognito-subject")
    assert cache.calls == [False]


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"token_use": "id", "aud": "client-id"},
        {"client_id": "another-client"},
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
    ],
)
async def test_access_token_rejects_wrong_use_client_or_expiry(claim_overrides: dict) -> None:
    token, cache = _signed_token(claims=_claims(**claim_overrides))

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _verifier(cache).verify_access_token(token)


async def test_onboarding_id_token_validates_audience_verified_email_and_display_name() -> None:
    token, cache = _signed_token(
        claims=_claims(
            token_use="id",
            aud="client-id",
            email="family@example.test",
            email_verified=True,
            name="  Lin Family  ",
        )
    )

    identity = await _verifier(cache).verify_id_token(token)

    assert identity.subject == "cognito-subject"
    assert identity.email == "family@example.test"
    assert identity.email_verified is True
    assert identity.display_name == "Lin Family"


async def test_onboarding_id_token_rejects_unverified_email() -> None:
    token, cache = _signed_token(
        claims=_claims(
            token_use="id",
            aud="client-id",
            email="family@example.test",
            email_verified="true",
        )
    )

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _verifier(cache).verify_id_token(token)


async def test_id_token_rejection_logs_only_a_bounded_claim_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    token, cache = _signed_token(
        claims=_claims(
            token_use="id",
            aud="client-id",
            email="restricted-family@example.test",
            email_verified="true",
        )
    )
    caplog.set_level(logging.WARNING, logger="app.adapters.auth.cognito")

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _verifier(cache).verify_id_token(token)

    assert "reason=IDENTITY_CLAIMS expected_token_use=id" in caplog.text
    assert token not in caplog.text
    assert "restricted-family@example.test" not in caplog.text


async def test_id_token_audience_rejection_logs_only_a_bounded_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    token, cache = _signed_token(
        claims=_claims(
            token_use="id",
            aud="another-client",
            email="restricted-family@example.test",
            email_verified=True,
        )
    )
    caplog.set_level(logging.WARNING, logger="app.adapters.auth.cognito")

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _verifier(cache).verify_id_token(token)

    assert "reason=AUDIENCE expected_token_use=id" in caplog.text
    assert token not in caplog.text
    assert "restricted-family@example.test" not in caplog.text


class _SessionContext:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _SessionFactory:
    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return _SessionContext(self._session)


async def test_database_resolver_uses_active_actor_and_single_tenant_membership() -> None:
    actor = type(
        "Actor",
        (),
        {"id": uuid4(), "actor_type": "FAMILY_MEMBER", "status": "ACTIVE"},
    )()
    membership = type("Membership", (), {"tenant_id": uuid4()})()
    actor_result = type("Result", (), {"scalar_one_or_none": lambda self: actor})()
    membership_result = type(
        "Result",
        (),
        {"scalars": lambda self: type("Scalars", (), {"all": lambda self: [membership]})()},
    )()
    session = AsyncMock()
    session.execute.side_effect = [actor_result, membership_result]

    resolver = DatabaseCognitoActorContextResolver(_SessionFactory(session))
    identity = VerifiedCognitoIdentity(subject="cognito-subject")
    context = await resolver.resolve_actor_context(identity)

    assert context == ActorContext(
        actor_id=actor.id,
        actor_role="FAMILY_MEMBER",
        tenant_id=membership.tenant_id,
        status="ACTIVE",
    )
    membership_statement = session.execute.await_args_list[1].args[0]
    sql = str(membership_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "JOIN eldercare_ai.tenant" in sql
    assert "eldercare_ai.tenant.status = 'ACTIVE'" in sql


async def test_database_resolver_fails_closed_for_ambiguous_tenant_membership() -> None:
    actor = type(
        "Actor",
        (),
        {"id": uuid4(), "actor_type": "FAMILY_MEMBER", "status": "ACTIVE"},
    )()
    actor_result = type("Result", (), {"scalar_one_or_none": lambda self: actor})()
    memberships_result = type(
        "Result",
        (),
        {
            "scalars": lambda self: type(
                "Scalars",
                (),
                {"all": lambda self: [object(), object()]},
            )()
        },
    )()
    session = AsyncMock()
    session.execute.side_effect = [actor_result, memberships_result]

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await DatabaseCognitoActorContextResolver(_SessionFactory(session)).resolve_actor_context(
            VerifiedCognitoIdentity(subject="cognito-subject")
        )
