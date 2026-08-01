"""Authentication abstractions and environment-guarded factory.

Defines:
- ActorContext: immutable identity derived from authentication
- Authenticator ABC: pluggable interface for auth providers
- FakeAuthenticator: configurable authenticator for tests and local dev
- NoAuthenticatorConfiguredError: raised when no auth is configured
- get_authenticator(): environment-guarded factory
- get_actor_context(): FastAPI dependency for protected routes
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from fastapi import Depends, Request

from app.core.config import AppEnv, get_settings
from app.core.exceptions import AuthenticationError


@dataclass(frozen=True)
class ActorContext:
    """Immutable identity context derived from authentication.

    Actor identity is derived ONLY from the authenticator — never from
    request body, query parameters, or headers directly.
    """

    actor_id: uuid.UUID
    actor_role: str
    tenant_id: uuid.UUID
    status: str = "ACTIVE"


class Authenticator(ABC):
    """Pluggable authenticator interface.

    Concrete implementations:
    - FakeAuthenticator (tests + explicit local dev)
    - CognitoAuthenticator (future production spec)
    """

    @abstractmethod
    async def authenticate(self, request: Request) -> ActorContext:
        """Extract and validate credentials, return ActorContext.

        Raises:
            AuthenticationError: if credentials are missing or invalid.
        """
        ...


class FakeAuthenticator(Authenticator):
    """Test/dev authenticator returning configurable ActorContext.

    Safety:
    - MAY be used in tests (always, via dependency override).
    - MAY be enabled in local development (APP_ENV=development)
      with explicit FAKE_AUTH_ENABLED=true config flag.
    - MUST NEVER be active in production.
    """

    def __init__(
        self,
        actor_id: uuid.UUID | None = None,
        actor_role: str = "care_worker",
        tenant_id: uuid.UUID | None = None,
        status: str = "ACTIVE",
    ) -> None:
        self._actor_id = actor_id or uuid.uuid4()
        self._actor_role = actor_role
        self._tenant_id = tenant_id or uuid.uuid4()
        self._status = status

    async def authenticate(self, request: Request) -> ActorContext:
        return ActorContext(
            actor_id=self._actor_id,
            actor_role=self._actor_role,
            tenant_id=self._tenant_id,
            status=self._status,
        )


class NoAuthenticatorConfiguredError(Exception):
    """Raised at startup when no real authenticator is configured.

    In production this means protected endpoints will fail closed (401).
    """

    pass


def get_authenticator() -> Authenticator:
    """Factory function for resolving the active authenticator.

    Rules:
    - In tests: FakeAuthenticator is injected via FastAPI dependency override.
      This function is never called directly in tests.
    - In development (APP_ENV=development) with FAKE_AUTH_ENABLED=true:
      Returns FakeAuthenticator for local dev convenience.
    - In production (APP_ENV=production):
      Returns the configured real authenticator.
      If no real authenticator is configured, raises
      NoAuthenticatorConfiguredError — protected endpoints will
      fail closed (HTTP 401 for all requests).
    - NEVER defaults to FakeAuthenticator in production.
    """
    settings = get_settings()

    if settings.app_env == AppEnv.PRODUCTION:
        # In production: require a real authenticator or fail closed
        real_authenticator = _resolve_production_authenticator(settings)
        if real_authenticator is None:
            raise NoAuthenticatorConfiguredError(
                "No authenticator configured for production. "
                "Protected endpoints will reject all requests."
            )
        return real_authenticator

    # Development mode
    if settings.fake_auth_enabled:
        if settings.fake_auth_actor_id is None or settings.fake_auth_tenant_id is None:
            raise NoAuthenticatorConfiguredError(
                "Fake authentication requires server-side actor and tenant IDs"
            )
        return FakeAuthenticator(
            actor_id=settings.fake_auth_actor_id,
            actor_role=settings.fake_auth_actor_role,
            tenant_id=settings.fake_auth_tenant_id,
        )

    # Development without fake auth — still require real config or fail
    real_authenticator = _resolve_production_authenticator(settings)
    if real_authenticator is None:
        raise NoAuthenticatorConfiguredError(
            "No authenticator configured. Set FAKE_AUTH_ENABLED=true "
            "for local development or configure a real authenticator."
        )
    return real_authenticator


def _resolve_production_authenticator(settings) -> Authenticator | None:
    """Resolve real authenticator from config. Returns None if not configured.

    Future: will return CognitoAuthenticator when that spec is implemented.
    """
    # Placeholder — no real authenticator in this foundation spec
    return None


async def get_actor_context(
    request: Request,
    authenticator: Authenticator = Depends(get_authenticator),
) -> ActorContext:
    """FastAPI dependency for protected routes.

    Calls the authenticator to resolve the actor's identity. On failure,
    raises AuthenticationError which maps to HTTP 401.
    """
    try:
        return await authenticator.authenticate(request)
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError("Authentication failed") from exc
