"""Unit tests for app/middleware/auth.py.

Tests ActorContext immutability, FakeAuthenticator behavior,
get_authenticator() environment guards, and get_actor_context() dependency.
"""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request

from app.core.config import AppEnv
from app.core.exceptions import AuthenticationError
from app.middleware.auth import (
    ActorContext,
    Authenticator,
    FakeAuthenticator,
    NoAuthenticatorConfiguredError,
    get_actor_context,
    get_authenticator,
)

# ─── ActorContext Tests ──────────────────────────────────────────────────────


class TestActorContext:
    """Tests for the ActorContext frozen dataclass."""

    def test_creates_with_valid_fields(self):
        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        ctx = ActorContext(actor_id=actor_id, actor_role="care_worker", tenant_id=tenant_id)

        assert ctx.actor_id == actor_id
        assert ctx.actor_role == "care_worker"
        assert ctx.tenant_id == tenant_id

    def test_is_frozen_immutable(self):
        ctx = ActorContext(actor_id=uuid.uuid4(), actor_role="admin", tenant_id=uuid.uuid4())
        with pytest.raises(FrozenInstanceError):
            ctx.actor_id = uuid.uuid4()  # type: ignore[misc]

    def test_equality_by_value(self):
        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        ctx1 = ActorContext(actor_id=actor_id, actor_role="admin", tenant_id=tenant_id)
        ctx2 = ActorContext(actor_id=actor_id, actor_role="admin", tenant_id=tenant_id)
        assert ctx1 == ctx2

    def test_inequality_different_role(self):
        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        ctx1 = ActorContext(actor_id=actor_id, actor_role="admin", tenant_id=tenant_id)
        ctx2 = ActorContext(actor_id=actor_id, actor_role="care_worker", tenant_id=tenant_id)
        assert ctx1 != ctx2


# ─── FakeAuthenticator Tests ────────────────────────────────────────────────


class TestFakeAuthenticator:
    """Tests for FakeAuthenticator."""

    def test_is_authenticator_subclass(self):
        assert issubclass(FakeAuthenticator, Authenticator)

    @pytest.mark.asyncio
    async def test_returns_configured_actor_context(self):
        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        auth = FakeAuthenticator(actor_id=actor_id, actor_role="admin", tenant_id=tenant_id)
        request = AsyncMock(spec=Request)

        ctx = await auth.authenticate(request)

        assert ctx.actor_id == actor_id
        assert ctx.actor_role == "admin"
        assert ctx.tenant_id == tenant_id

    @pytest.mark.asyncio
    async def test_defaults_generate_uuids(self):
        auth = FakeAuthenticator()
        request = AsyncMock(spec=Request)

        ctx = await auth.authenticate(request)

        assert isinstance(ctx.actor_id, uuid.UUID)
        assert isinstance(ctx.tenant_id, uuid.UUID)
        assert ctx.actor_role == "care_worker"

    @pytest.mark.asyncio
    async def test_returns_same_context_on_repeated_calls(self):
        auth = FakeAuthenticator()
        request = AsyncMock(spec=Request)

        ctx1 = await auth.authenticate(request)
        ctx2 = await auth.authenticate(request)

        assert ctx1 == ctx2


# ─── get_authenticator() Factory Tests ──────────────────────────────────────


class TestGetAuthenticator:
    """Tests for the environment-guarded get_authenticator() factory."""

    def _mock_settings(self, app_env: AppEnv, fake_auth_enabled: bool = False):
        """Create a mock settings object."""
        mock = AsyncMock()
        mock.app_env = app_env
        mock.fake_auth_enabled = fake_auth_enabled
        mock.fake_auth_actor_id = None
        mock.fake_auth_tenant_id = None
        mock.fake_auth_actor_role = "care_worker"
        return mock

    @patch("app.middleware.auth.get_settings")
    def test_production_no_real_auth_raises(self, mock_get_settings):
        """Production without real authenticator raises NoAuthenticatorConfiguredError."""
        mock_get_settings.return_value = self._mock_settings(AppEnv.PRODUCTION)

        with pytest.raises(NoAuthenticatorConfiguredError):
            get_authenticator()

    @patch("app.middleware.auth.get_settings")
    def test_production_ignores_fake_auth_flag(self, mock_get_settings):
        """Production NEVER uses FakeAuthenticator even if flag is set."""
        mock_get_settings.return_value = self._mock_settings(
            AppEnv.PRODUCTION, fake_auth_enabled=True
        )

        with pytest.raises(NoAuthenticatorConfiguredError):
            get_authenticator()

    @patch("app.middleware.auth.get_settings")
    def test_development_with_fake_auth_returns_fake(self, mock_get_settings):
        """Development + FAKE_AUTH_ENABLED=true returns FakeAuthenticator."""
        settings = self._mock_settings(AppEnv.DEVELOPMENT, fake_auth_enabled=True)
        settings.fake_auth_actor_id = uuid.uuid4()
        settings.fake_auth_tenant_id = uuid.uuid4()
        mock_get_settings.return_value = settings

        authenticator = get_authenticator()

        assert isinstance(authenticator, FakeAuthenticator)

    @patch("app.middleware.auth.get_settings")
    def test_development_fake_auth_without_server_scope_fails_closed(self, mock_get_settings):
        """The dev flag alone must not mint random actor or tenant authority."""
        mock_get_settings.return_value = self._mock_settings(
            AppEnv.DEVELOPMENT, fake_auth_enabled=True
        )

        with pytest.raises(NoAuthenticatorConfiguredError):
            get_authenticator()

    @patch("app.middleware.auth.get_settings")
    def test_development_fake_auth_uses_server_configured_scope(self, mock_get_settings):
        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        settings = self._mock_settings(AppEnv.DEVELOPMENT, fake_auth_enabled=True)
        settings.fake_auth_actor_id = actor_id
        settings.fake_auth_tenant_id = tenant_id
        settings.fake_auth_actor_role = "ELDER"
        mock_get_settings.return_value = settings

        authenticator = get_authenticator()

        assert authenticator._actor_id == actor_id
        assert authenticator._tenant_id == tenant_id
        assert authenticator._actor_role == "ELDER"

    @patch("app.middleware.auth.get_settings")
    def test_development_without_fake_auth_raises(self, mock_get_settings):
        """Development without fake auth and no real auth raises."""
        mock_get_settings.return_value = self._mock_settings(
            AppEnv.DEVELOPMENT, fake_auth_enabled=False
        )

        with pytest.raises(NoAuthenticatorConfiguredError):
            get_authenticator()

    @patch("app.middleware.auth._resolve_production_authenticator")
    @patch("app.middleware.auth.get_settings")
    def test_production_with_real_auth_returns_it(self, mock_get_settings, mock_resolve):
        """Production with real authenticator configured returns it."""
        mock_get_settings.return_value = self._mock_settings(AppEnv.PRODUCTION)
        real_auth = FakeAuthenticator()  # stand-in for a real authenticator
        mock_resolve.return_value = real_auth

        authenticator = get_authenticator()

        assert authenticator is real_auth

    @patch("app.middleware.auth._resolve_production_authenticator")
    @patch("app.middleware.auth.get_settings")
    def test_development_without_fake_but_with_real_returns_it(
        self, mock_get_settings, mock_resolve
    ):
        """Development without fake auth but with real config returns real."""
        mock_get_settings.return_value = self._mock_settings(
            AppEnv.DEVELOPMENT, fake_auth_enabled=False
        )
        real_auth = FakeAuthenticator()  # stand-in
        mock_resolve.return_value = real_auth

        authenticator = get_authenticator()

        assert authenticator is real_auth


# ─── get_actor_context() Dependency Tests ───────────────────────────────────


class TestGetActorContext:
    """Tests for the get_actor_context FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_returns_actor_context_from_authenticator(self):
        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        auth = FakeAuthenticator(actor_id=actor_id, actor_role="admin", tenant_id=tenant_id)
        request = AsyncMock(spec=Request)

        ctx = await get_actor_context(request=request, authenticator=auth)

        assert ctx.actor_id == actor_id
        assert ctx.actor_role == "admin"
        assert ctx.tenant_id == tenant_id

    @pytest.mark.asyncio
    async def test_raises_authentication_error_on_failure(self):
        """If authenticator raises, get_actor_context raises AuthenticationError."""

        class FailingAuth(Authenticator):
            async def authenticate(self, request: Request) -> ActorContext:
                raise RuntimeError("token expired")

        request = AsyncMock(spec=Request)

        with pytest.raises(AuthenticationError):
            await get_actor_context(request=request, authenticator=FailingAuth())

    @pytest.mark.asyncio
    async def test_propagates_authentication_error_directly(self):
        """If authenticator raises AuthenticationError, it propagates unchanged."""

        class AuthErrorAuth(Authenticator):
            async def authenticate(self, request: Request) -> ActorContext:
                raise AuthenticationError("Invalid token")

        request = AsyncMock(spec=Request)

        with pytest.raises(AuthenticationError, match="Invalid token"):
            await get_actor_context(request=request, authenticator=AuthErrorAuth())
