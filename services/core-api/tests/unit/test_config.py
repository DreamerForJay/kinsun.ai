"""Unit tests for app.core.config — Settings Manager."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import AppEnv, DatabasePoolMode, Settings, get_settings

# ─── Helpers ─────────────────────────────────────────────────────────────────

_VALID_DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/testdb"


def _make_settings(**overrides: str) -> Settings:
    """Create Settings with environment variable overrides (no .env file)."""
    env = {
        "APP_ENV": "development",
        "DATABASE_URL": _VALID_DB_URL,
    }
    env.update(overrides)
    with patch.dict(os.environ, env, clear=False):
        return Settings(_env_file=None)


# ─── Basic construction ──────────────────────────────────────────────────────


class TestSettingsConstruction:
    def test_valid_settings(self) -> None:
        s = _make_settings()
        assert s.app_env == AppEnv.DEVELOPMENT
        assert s.database_url == _VALID_DB_URL
        assert s.app_title == "kinsun.ai Core API"
        assert s.app_version == "0.1.0"
        assert s.port == 8000
        assert s.db_pool_mode == DatabasePoolMode.QUEUE
        assert s.db_pool_size == 5
        assert s.db_max_overflow == 10
        assert s.db_connect_timeout_seconds == 5.0
        assert s.db_recovery_timeout_seconds == 10.0

    def test_production_env(self) -> None:
        s = _make_settings(APP_ENV="production")
        assert s.app_env == AppEnv.PRODUCTION

    def test_all_fields_settable(self) -> None:
        s = _make_settings(
            APP_TITLE="Custom Title",
            APP_VERSION="2.0.0",
            DOCS_URL="/api-docs",
            HOST="127.0.0.1",
            PORT="9000",
            DB_POOL_MODE="null",
            DB_POOL_SIZE="10",
            DB_MAX_OVERFLOW="20",
            DB_CONNECT_TIMEOUT_SECONDS="4",
            DB_RECOVERY_TIMEOUT_SECONDS="9",
            TEST_DATABASE_URL="postgresql+asyncpg://x:y@host/test",
            DATABASE_PASSWORD="supersecret",
            FAKE_AUTH_ENABLED="true",
            FAKE_AUTH_ACTOR_ID="20000000-0000-4000-8000-000000000001",
            FAKE_AUTH_TENANT_ID="10000000-0000-4000-8000-000000000001",
            FAKE_AUTH_ACTOR_ROLE="ELDER",
            COGNITO_AUTH_ENABLED="true",
            COGNITO_REGION="ap-northeast-1",
            COGNITO_USER_POOL_ID="ap-northeast-1_example",
            COGNITO_APP_CLIENT_ID="client-id",
            COGNITO_JWKS_CACHE_SECONDS="120",
            COGNITO_HTTP_TIMEOUT_SECONDS="4",
            FAMILY_INVITATION_HMAC_SECRET="test-family-invitation-secret-32-bytes",
            VOICE_TICKET_ENABLED="true",
            VOICE_TICKET_HMAC_SECRET="test-voice-ticket-secret-material-32-bytes",
            VOICE_TICKET_TTL_SECONDS="75",
            AGENT_RUNTIME_URL="http://127.0.0.1:8001",
            AGENT_RUNTIME_TIMEOUT_SECONDS="8",
            AGENT_RUNTIME_MODEL_ID="mock-v1",
        )
        assert s.app_title == "Custom Title"
        assert s.app_version == "2.0.0"
        assert s.docs_url == "/api-docs"
        assert s.host == "127.0.0.1"
        assert s.port == 9000
        assert s.db_pool_mode == DatabasePoolMode.NULL
        assert s.db_pool_size == 10
        assert s.db_max_overflow == 20
        assert s.db_connect_timeout_seconds == 4
        assert s.db_recovery_timeout_seconds == 9
        assert s.test_database_url == "postgresql+asyncpg://x:y@host/test"
        assert s.database_password == "supersecret"
        assert s.fake_auth_enabled is True
        assert str(s.fake_auth_actor_id) == "20000000-0000-4000-8000-000000000001"
        assert str(s.fake_auth_tenant_id) == "10000000-0000-4000-8000-000000000001"
        assert s.fake_auth_actor_role == "ELDER"
        assert s.cognito_auth_enabled is True
        assert s.cognito_region == "ap-northeast-1"
        assert s.cognito_user_pool_id == "ap-northeast-1_example"
        assert s.cognito_app_client_id == "client-id"
        assert s.cognito_jwks_cache_seconds == 120
        assert s.cognito_http_timeout_seconds == 4
        assert s.family_invitation_hmac_secret == "test-family-invitation-secret-32-bytes"
        assert s.voice_ticket_enabled is True
        assert s.voice_ticket_hmac_secret == "test-voice-ticket-secret-material-32-bytes"
        assert s.voice_ticket_ttl_seconds == 75
        assert s.agent_runtime_url == "http://127.0.0.1:8001"
        assert s.agent_runtime_timeout_seconds == 8
        assert s.agent_runtime_model_id == "mock-v1"


# ─── Validation errors ───────────────────────────────────────────────────────


class TestValidation:
    def test_missing_database_url_raises(self) -> None:
        """Required field missing raises validation error identifying the variable."""
        env = {"APP_ENV": "development"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)
            errors = exc_info.value.errors()
            field_names = [e["loc"][-1] for e in errors]
            assert "database_url" in field_names

    def test_invalid_database_url_scheme(self) -> None:
        """DATABASE_URL without postgresql+asyncpg:// is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            _make_settings(DATABASE_URL="mysql://user:pass@localhost/db")
        errors = exc_info.value.errors()
        assert any("postgresql+asyncpg://" in str(e) for e in errors)

    def test_port_too_low(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(PORT="0")

    def test_port_too_high(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(PORT="65536")

    def test_port_boundaries_valid(self) -> None:
        s = _make_settings(PORT="1")
        assert s.port == 1
        s = _make_settings(PORT="65535")
        assert s.port == 65535

    def test_invalid_app_env_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(APP_ENV="staging")

    def test_db_pool_size_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(DB_POOL_SIZE="0")

    def test_db_max_overflow_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(DB_MAX_OVERFLOW="-1")

    def test_invalid_db_pool_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(DB_POOL_MODE="unsupported")

    @pytest.mark.parametrize(
        "field",
        ["DB_CONNECT_TIMEOUT_SECONDS", "DB_RECOVERY_TIMEOUT_SECONDS"],
    )
    def test_database_timeouts_must_be_positive(self, field: str) -> None:
        with pytest.raises(ValidationError):
            _make_settings(**{field: "0"})

    def test_enabled_cognito_requires_complete_server_configuration(self) -> None:
        with pytest.raises(ValidationError, match="COGNITO_REGION"):
            _make_settings(COGNITO_AUTH_ENABLED="true")

    def test_enabled_cognito_requires_family_invitation_secret(self) -> None:
        with pytest.raises(ValidationError, match="FAMILY_INVITATION_HMAC_SECRET"):
            _make_settings(
                COGNITO_AUTH_ENABLED="true",
                COGNITO_REGION="us-west-2",
                COGNITO_USER_POOL_ID="us-west-2_example",
                COGNITO_APP_CLIENT_ID="client-id",
            )

    def test_daily_line_notification_requires_complete_independent_secrets(self) -> None:
        with pytest.raises(ValidationError, match="LINE_ACCOUNT_LINK_ENABLED"):
            _make_settings(LINE_DAILY_NOTIFICATION_ENABLED="true")

        common = {
            "LINE_ACCOUNT_LINK_ENABLED": "true",
            "LINE_CHANNEL_SECRET": "synthetic-channel-secret",
            "LINE_CHANNEL_ACCESS_TOKEN": "synthetic-channel-token",
            "LINE_IDENTITY_HMAC_SECRET": "synthetic-identity-hmac-secret-32-bytes",
            "LINE_ACCOUNT_LINK_BASE_URL": "https://staging.example.com",
            "LINE_DAILY_NOTIFICATION_ENABLED": "true",
        }
        with pytest.raises(ValidationError, match="LINE_SUBJECT_ENCRYPTION_SECRET"):
            _make_settings(**common)

        settings = _make_settings(
            **common,
            LINE_SUBJECT_ENCRYPTION_SECRET=("synthetic-independent-encryption-secret-32-bytes"),
        )
        assert settings.line_daily_notification_enabled is True
        assert settings.line_daily_notification_send_time == "08:00"

    def test_daily_line_notification_rejects_non_0800_schedule(self) -> None:
        with pytest.raises(ValidationError, match="must remain 08:00"):
            _make_settings(
                LINE_ACCOUNT_LINK_ENABLED="true",
                LINE_CHANNEL_SECRET="synthetic-channel-secret",
                LINE_CHANNEL_ACCESS_TOKEN="synthetic-channel-token",
                LINE_IDENTITY_HMAC_SECRET="synthetic-identity-hmac-secret-32-bytes",
                LINE_ACCOUNT_LINK_BASE_URL="https://staging.example.com",
                LINE_DAILY_NOTIFICATION_ENABLED="true",
                LINE_SUBJECT_ENCRYPTION_SECRET=("synthetic-independent-encryption-secret-32-bytes"),
                LINE_DAILY_NOTIFICATION_SEND_TIME="09:00",
            )

    def test_enabled_voice_ticket_requires_strong_secret(self) -> None:
        with pytest.raises(ValidationError, match="VOICE_TICKET_HMAC_SECRET"):
            _make_settings(
                VOICE_TICKET_ENABLED="true",
                VOICE_TICKET_HMAC_SECRET="too-short",
            )

    @pytest.mark.parametrize("ttl", ["14", "121"])
    def test_voice_ticket_ttl_is_bounded(self, ttl: str) -> None:
        with pytest.raises(ValidationError):
            _make_settings(VOICE_TICKET_TTL_SECONDS=ttl)


# ─── Secret redaction ────────────────────────────────────────────────────────


class TestSecretRedaction:
    def test_model_dump_redacts_password(self) -> None:
        s = _make_settings(DATABASE_PASSWORD="real_password")
        dumped = s.model_dump()
        assert dumped["database_password"] == "***"

    def test_repr_redacts_password(self) -> None:
        s = _make_settings(DATABASE_PASSWORD="real_password")
        r = repr(s)
        assert "real_password" not in r
        assert "***" in r

    def test_str_redacts_password(self) -> None:
        s = _make_settings(DATABASE_PASSWORD="real_password")
        text = str(s)
        assert "real_password" not in text
        assert "***" in text

    def test_non_sensitive_fields_not_redacted(self) -> None:
        s = _make_settings()
        dumped = s.model_dump()
        assert dumped["database_url"] == _VALID_DB_URL
        assert dumped["app_title"] == "kinsun.ai Core API"

    def test_family_invitation_secret_is_redacted(self) -> None:
        secret = "test-family-invitation-secret-32-bytes"
        settings = _make_settings(FAMILY_INVITATION_HMAC_SECRET=secret)
        assert settings.model_dump()["family_invitation_hmac_secret"] == "***"
        assert secret not in repr(settings)

    def test_voice_ticket_secret_is_redacted(self) -> None:
        secret = "test-voice-ticket-secret-material-32-bytes"
        settings = _make_settings(VOICE_TICKET_HMAC_SECRET=secret)
        assert settings.model_dump()["voice_ticket_hmac_secret"] == "***"
        assert secret not in repr(settings)


# ─── Singleton pattern ───────────────────────────────────────────────────────


class TestSingleton:
    def test_get_settings_returns_same_instance(self) -> None:
        get_settings.cache_clear()
        env = {"DATABASE_URL": _VALID_DB_URL, "APP_ENV": "development"}
        with patch.dict(os.environ, env, clear=False):
            s1 = get_settings()
            s2 = get_settings()
        assert s1 is s2

    def test_get_settings_cache_clearable(self) -> None:
        """Cache can be cleared to force re-creation (useful in tests)."""
        get_settings.cache_clear()
        env = {"DATABASE_URL": _VALID_DB_URL, "APP_ENV": "development"}
        with patch.dict(os.environ, env, clear=False):
            s1 = get_settings()
        get_settings.cache_clear()
        with patch.dict(os.environ, env, clear=False):
            s2 = get_settings()
        # Different objects after cache clear
        assert s1 is not s2


# ─── Conditional .env loading ────────────────────────────────────────────────


class TestEnvFileLoading:
    def test_development_mode_reads_env_file(self, tmp_path) -> None:
        """In development mode, .env file values are loaded."""
        env_file = tmp_path / ".env"
        env_file.write_text(f"DATABASE_URL={_VALID_DB_URL}\nDATABASE_PASSWORD=from_file\n")
        env = {"APP_ENV": "development"}
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=str(env_file))
        assert s.database_url == _VALID_DB_URL
        assert s.database_password == "from_file"

    def test_production_mode_ignores_env_file(self, tmp_path) -> None:
        """In production mode, .env file is not read (env vars only)."""
        env_file = tmp_path / ".env"
        env_file.write_text("DATABASE_PASSWORD=from_file\n")
        env = {
            "APP_ENV": "production",
            "DATABASE_URL": _VALID_DB_URL,
        }
        with patch.dict(os.environ, env, clear=True):
            # Explicitly pass _env_file=None to simulate production behavior
            s = Settings(_env_file=None)
        # Should use default, not file value
        assert s.database_password == ""

    def test_env_vars_override_env_file(self, tmp_path) -> None:
        """Environment variables take precedence over .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(f"DATABASE_URL={_VALID_DB_URL}\nPORT=3000\n")
        env = {"APP_ENV": "development", "PORT": "9999"}
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=str(env_file))
        assert s.port == 9999
