"""Cognito JWT verification and formal Core actor resolution.

Only the Cognito ``sub`` (and, for onboarding, a verified email) leaves token
validation.  Role, tenant and actor status always come from Core's database.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from fastapi import Request
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    MissingRequiredClaimError,
)
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AuthenticationError
from app.middleware.auth import ActorContext, Authenticator
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant
from app.repositories.actor_repo import ActorRepository

_AUTHENTICATION_REQUIRED = "Authentication required"
logger = logging.getLogger(__name__)


class _InvalidCognitoHeaderError(Exception):
    """Internal marker for a rejected, untrusted JWT header."""


def _jwt_rejection_reason(exc: Exception) -> str:
    """Map provider exceptions to bounded diagnostics without their messages."""
    if isinstance(exc, _InvalidCognitoHeaderError):
        return "HEADER"
    if isinstance(exc, ExpiredSignatureError):
        return "EXPIRED"
    if isinstance(exc, InvalidAudienceError):
        return "AUDIENCE"
    if isinstance(exc, InvalidIssuerError):
        return "ISSUER"
    if isinstance(exc, InvalidSignatureError):
        return "SIGNATURE"
    if isinstance(exc, MissingRequiredClaimError):
        return "REQUIRED_CLAIM"
    if isinstance(exc, AuthenticationError):
        return "JWKS"
    if isinstance(exc, InvalidTokenError):
        return "INVALID_TOKEN"
    return "INVALID_TOKEN"


def _log_token_rejection(reason: str, expected_token_use: str) -> None:
    logger.warning(
        "Cognito token rejected reason=%s expected_token_use=%s",
        reason,
        expected_token_use,
    )


@dataclass(frozen=True)
class VerifiedCognitoIdentity:
    """Minimal identity returned only after an access token is verified.

    Actor role, tenant, and status are intentionally absent. Those values are
    formal Core state and must be loaded by ``CognitoActorContextResolver``;
    they must not be copied from request data or unverified JWT claims.
    """

    subject: str
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not self.subject or self.subject != self.subject.strip():
            raise ValueError("Cognito subject must be a non-empty normalized string")
        if self.email is not None and (not self.email or self.email != self.email.strip()):
            raise ValueError("Cognito email must be a non-empty normalized string")
        if self.display_name is not None:
            normalized_display_name = self.display_name.strip()
            if len(normalized_display_name) > 120:
                raise ValueError("Cognito display name must be at most 120 characters")
            object.__setattr__(
                self,
                "display_name",
                normalized_display_name or None,
            )


class CognitoTokenVerifier(ABC):
    """Cryptographic Cognito access-token verification interface.

    A production implementation must validate the signature against the
    configured User Pool JWKS as well as issuer, expiration, ``token_use``
    (access), and application client identity. It must never return raw token
    claims as an authenticated ``ActorContext``.
    """

    @abstractmethod
    async def verify_access_token(self, token: str) -> VerifiedCognitoIdentity:
        """Verify one opaque bearer token and return its trusted subject."""
        ...

    @abstractmethod
    async def verify_id_token(self, token: str) -> VerifiedCognitoIdentity:
        """Verify an onboarding ID token including audience and verified email."""
        ...


class CognitoActorContextResolver(ABC):
    """Resolve a verified Cognito subject to formal Core identity state.

    Implementations must use a server-side source of truth to resolve actor ID,
    role, tenant membership, and actor status. Tenant-selection and membership
    policy belong here or in a delegated Core service, never in request headers,
    query parameters, bodies, or unverified claims.
    """

    @abstractmethod
    async def resolve_actor_context(self, identity: VerifiedCognitoIdentity) -> ActorContext:
        """Return the formal actor context for a verified Cognito identity."""
        ...


class CognitoJwksCache:
    """Small process-local JWKS cache with an unknown-key rotation refresh."""

    def __init__(self, jwks_url: str, *, ttl_seconds: int, timeout_seconds: float) -> None:
        self._jwks_url = jwks_url
        self._ttl = timedelta(seconds=ttl_seconds)
        self._timeout = timeout_seconds
        self._keys: dict[str, dict[str, Any]] = {}
        self._expires_at = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()

    async def get(self, kid: str, *, force_refresh: bool = False) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not force_refresh and now < self._expires_at and kid in self._keys:
            return self._keys[kid]

        async with self._lock:
            now = datetime.now(UTC)
            if not force_refresh and now < self._expires_at and kid in self._keys:
                return self._keys[kid]
            await self._refresh()
            key = self._keys.get(kid)
            if key is None:
                raise AuthenticationError(_AUTHENTICATION_REQUIRED)
            return key

    async def _refresh(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self._jwks_url)
                response.raise_for_status()
                document = response.json()
            keys = document.get("keys") if isinstance(document, dict) else None
            if not isinstance(keys, list):
                raise ValueError("JWKS response has no keys")
            parsed = {
                key["kid"]: key
                for key in keys
                if isinstance(key, dict)
                and isinstance(key.get("kid"), str)
                and key.get("kty") == "RSA"
            }
            if not parsed:
                raise ValueError("JWKS response has no usable RSA keys")
        except Exception as exc:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from exc

        self._keys = parsed
        self._expires_at = datetime.now(UTC) + self._ttl


class CognitoJwtVerifier(CognitoTokenVerifier):
    """Verify RS256 Cognito access and onboarding ID tokens against JWKS."""

    def __init__(
        self,
        *,
        region: str,
        user_pool_id: str,
        app_client_id: str,
        jwks_cache_seconds: int = 300,
        http_timeout_seconds: float = 5.0,
        jwks_cache: CognitoJwksCache | None = None,
    ) -> None:
        if not all((region.strip(), user_pool_id.strip(), app_client_id.strip())):
            raise ValueError("Cognito region, user pool ID, and app client ID are required")
        self._issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        self._app_client_id = app_client_id
        self._jwks_cache = jwks_cache or CognitoJwksCache(
            f"{self._issuer}/.well-known/jwks.json",
            ttl_seconds=jwks_cache_seconds,
            timeout_seconds=http_timeout_seconds,
        )

    async def verify_access_token(self, token: str) -> VerifiedCognitoIdentity:
        claims = await self._decode(token, token_use="access")
        if claims.get("client_id") != self._app_client_id:
            _log_token_rejection("CLIENT_ID", "access")
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        try:
            subject = _required_subject(claims)
        except AuthenticationError:
            _log_token_rejection("SUBJECT", "access")
            raise
        return VerifiedCognitoIdentity(subject=subject)

    async def verify_id_token(self, token: str) -> VerifiedCognitoIdentity:
        claims = await self._decode(token, token_use="id", verify_audience=True)
        email = claims.get("email")
        if (
            not isinstance(email, str)
            or not email.strip()
            or claims.get("email_verified") is not True
        ):
            _log_token_rejection("IDENTITY_CLAIMS", "id")
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        try:
            return VerifiedCognitoIdentity(
                subject=_required_subject(claims),
                email=email,
                email_verified=True,
                display_name=_optional_display_name(claims),
            )
        except (AuthenticationError, ValueError):
            _log_token_rejection("IDENTITY_CLAIMS", "id")
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None

    async def _decode(
        self,
        token: str,
        *,
        token_use: str,
        verify_audience: bool = False,
    ) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise _InvalidCognitoHeaderError
            kid = header["kid"]
            claims = await self._decode_with_key(
                token,
                await self._jwks_cache.get(kid),
                verify_audience=verify_audience,
            )
        except InvalidSignatureError:
            try:
                claims = await self._decode_with_key(
                    token,
                    await self._jwks_cache.get(kid, force_refresh=True),
                    verify_audience=verify_audience,
                )
            except Exception as exc:
                _log_token_rejection(_jwt_rejection_reason(exc), token_use)
                raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        except Exception as exc:
            _log_token_rejection(_jwt_rejection_reason(exc), token_use)
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None

        if claims.get("token_use") != token_use:
            _log_token_rejection("TOKEN_USE", token_use)
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        return claims

    async def _decode_with_key(
        self,
        token: str,
        jwk: dict[str, Any],
        *,
        verify_audience: bool,
    ) -> dict[str, Any]:
        key = RSAAlgorithm.from_jwk(json.dumps(jwk))
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=self._app_client_id if verify_audience else None,
            issuer=self._issuer,
            options={
                "require": ["exp", "iss", "sub", "token_use"],
                "verify_aud": verify_audience,
            },
        )


class DatabaseCognitoActorContextResolver(CognitoActorContextResolver):
    """Map only verified Cognito subjects to one active Core actor/tenant."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve_actor_context(self, identity: VerifiedCognitoIdentity) -> ActorContext:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            actor = await ActorRepository(session).get_active_by_cognito_sub(identity.subject)
            if actor is None:
                raise AuthenticationError(_AUTHENTICATION_REQUIRED)

            result = await session.execute(
                select(ActorTenantMembership)
                .join(Tenant, Tenant.id == ActorTenantMembership.tenant_id)
                .where(
                    ActorTenantMembership.actor_id == actor.id,
                    ActorTenantMembership.role_code == actor.actor_type,
                    ActorTenantMembership.care_unit_id.is_(None),
                    ActorTenantMembership.status == "ACTIVE",
                    ActorTenantMembership.effective_from <= now,
                    or_(
                        ActorTenantMembership.effective_to.is_(None),
                        now < ActorTenantMembership.effective_to,
                    ),
                    Tenant.status == "ACTIVE",
                )
            )
            memberships = list(result.scalars().all())

        if len(memberships) != 1:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        membership = memberships[0]
        return ActorContext(
            actor_id=actor.id,
            actor_role=actor.actor_type,
            tenant_id=membership.tenant_id,
            status=actor.status,
        )


def _required_subject(claims: dict[str, Any]) -> str:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject or subject != subject.strip():
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    return subject


def _optional_display_name(claims: dict[str, Any]) -> str | None:
    """Return only a bounded, normalized presentation value from an ID token."""
    display_name = claims.get("name")
    if display_name is None:
        return None
    if not isinstance(display_name, str):
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    normalized = display_name.strip()
    if len(normalized) > 120:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    return normalized or None


class CognitoAuthenticator(Authenticator):
    """Authenticate a request through injected Cognito provider boundaries.

    This class is safe to instantiate only when both dependencies have concrete
    production implementations. It normalizes every provider or lookup failure
    to the same public authentication error and never logs or returns the token.
    """

    def __init__(
        self,
        token_verifier: CognitoTokenVerifier,
        actor_context_resolver: CognitoActorContextResolver,
    ) -> None:
        self._token_verifier = token_verifier
        self._actor_context_resolver = actor_context_resolver

    async def authenticate(self, request: Request) -> ActorContext:
        token = _extract_bearer_token(request)

        try:
            identity = await self._token_verifier.verify_access_token(token)
            if not isinstance(identity, VerifiedCognitoIdentity):
                raise TypeError("Token verifier returned an invalid identity type")

            actor_context = await self._actor_context_resolver.resolve_actor_context(identity)
            if not isinstance(actor_context, ActorContext):
                raise TypeError("Actor resolver returned an invalid context type")

            return actor_context
        except Exception:
            pass

        raise AuthenticationError(_AUTHENTICATION_REQUIRED)


def _extract_bearer_token(request: Request) -> str:
    """Extract exactly one well-formed Bearer credential from a request."""
    authorization_values = request.headers.getlist("authorization")
    if len(authorization_values) != 1:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)

    scheme, separator, token = authorization_values[0].partition(" ")
    if (
        separator != " "
        or scheme.casefold() != "bearer"
        or not token
        or any(character.isspace() for character in token)
    ):
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)

    return token
