"""Application configuration management.

Loads settings from environment variables (and .env file in development mode).
Provides a singleton accessor via get_settings().
"""

from __future__ import annotations

import os
import re
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    """Application environment profiles."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class DatabasePoolMode(str, Enum):
    """Supported SQLAlchemy connection-pool strategies."""

    QUEUE = "queue"
    NULL = "null"


# Resolve the repository-level .env independently of the process working directory.
# In production we never read .env; in development we do (env vars still take precedence).
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_env_file: str | None = (
    str(_REPOSITORY_ROOT / ".env") if os.getenv("APP_ENV", "development") != "production" else None
)

# Substrings in field names that indicate sensitive data (used for redaction).
_SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "secret",
    "key",
    "token",
)


class Settings(BaseSettings):
    """Central application settings.

    All values come from environment variables. In development mode a .env file
    is also read (env vars take precedence over .env values).
    """

    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ─────────────────────────────────────────────────────────────
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_title: str = "kinsun.ai Core API"
    app_version: str = "0.1.0"
    docs_url: str = "/docs"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)

    # ─── Database ────────────────────────────────────────────────────────────────
    database_url: str  # Required — validated below
    db_pool_mode: DatabasePoolMode = DatabasePoolMode.QUEUE
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    db_recovery_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    # ─── Testing ─────────────────────────────────────────────────────────────────
    test_database_url: str = ""

    # ─── Secrets (redacted in output) ────────────────────────────────────────────
    database_password: str = ""

    # ─── Authentication ──────────────────────────────────────────────────────────
    fake_auth_enabled: bool = False
    fake_auth_actor_id: UUID | None = None
    fake_auth_tenant_id: UUID | None = None
    fake_auth_actor_role: str = Field(default="ELDER", min_length=1, max_length=64)
    cognito_auth_enabled: bool = False
    cognito_region: str = Field(default="", max_length=64)
    cognito_user_pool_id: str = Field(default="", max_length=256)
    cognito_app_client_id: str = Field(default="", max_length=256)
    cognito_jwks_cache_seconds: int = Field(default=300, ge=30, le=3600)
    cognito_http_timeout_seconds: float = Field(default=5.0, gt=0, le=15)
    family_invitation_hmac_secret: str = ""

    # ─── LINE Messaging API ──────────────────────────────────────────────────────
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_account_link_enabled: bool = False
    line_identity_hmac_secret: str = ""
    line_identity_hmac_key_version: int = Field(default=1, ge=1, le=2_147_483_647)
    line_account_link_base_url: str = Field(default="", max_length=2048)
    line_link_challenge_ttl_seconds: int = Field(default=600, ge=60, le=600)
    line_link_challenge_max_attempts: int = Field(default=3, ge=1, le=5)
    line_messaging_timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    line_subject_encryption_secret: str = ""
    line_daily_notification_enabled: bool = False
    line_daily_notification_timezone: str = Field(default="Asia/Taipei", max_length=64)
    line_daily_notification_send_time: str = Field(default="08:00", max_length=5)

    # ─── Internal service adapters ───────────────────────────────────────────────
    voice_ticket_enabled: bool = False
    voice_ticket_hmac_secret: str = ""
    voice_ticket_ttl_seconds: int = Field(default=60, ge=15, le=120)
    agent_runtime_url: str = "http://127.0.0.1:8001"
    agent_runtime_timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    agent_runtime_model_id: str = Field(default="mock", min_length=1, max_length=200)

    # ─── Validators ──────────────────────────────────────────────────────────────

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        return v

    @model_validator(mode="after")
    def validate_service_configuration(self) -> Settings:
        """Require complete server-owned auth and LINE settings when enabled."""
        if self.cognito_auth_enabled and not all(
            (
                self.cognito_region.strip(),
                self.cognito_user_pool_id.strip(),
                self.cognito_app_client_id.strip(),
            )
        ):
            raise ValueError(
                "COGNITO_REGION, COGNITO_USER_POOL_ID, and COGNITO_APP_CLIENT_ID "
                "are required when COGNITO_AUTH_ENABLED=true"
            )
        if (
            self.cognito_auth_enabled
            and len(self.family_invitation_hmac_secret.encode("utf-8")) < 32
        ):
            raise ValueError(
                "FAMILY_INVITATION_HMAC_SECRET must contain at least 32 bytes "
                "when COGNITO_AUTH_ENABLED=true"
            )

        if self.line_account_link_enabled:
            if not self.line_channel_secret.strip() or not self.line_channel_access_token.strip():
                raise ValueError(
                    "LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN are required "
                    "when LINE_ACCOUNT_LINK_ENABLED=true"
                )
            if len(self.line_identity_hmac_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "LINE_IDENTITY_HMAC_SECRET must contain at least 32 bytes "
                    "when LINE_ACCOUNT_LINK_ENABLED=true"
                )
            if self.line_identity_hmac_secret in {
                self.line_channel_secret,
                self.family_invitation_hmac_secret,
            }:
                raise ValueError(
                    "LINE_IDENTITY_HMAC_SECRET must be independent from LINE channel "
                    "and family invitation secrets"
                )
            if self.line_identity_hmac_key_version != 1:
                raise ValueError(
                    "LINE_IDENTITY_HMAC_KEY_VERSION must remain 1 for the MVP; "
                    "key rotation requires an explicit identity rekey migration"
                )
            base_url = self.line_account_link_base_url.strip().rstrip("/")
            authority = base_url.removeprefix("https://")
            if (
                not base_url.startswith("https://")
                or not authority
                or "/" in authority
                or "@" in authority
                or "?" in authority
                or "#" in authority
                or any(character.isspace() for character in authority)
            ):
                raise ValueError(
                    "LINE_ACCOUNT_LINK_BASE_URL must be a fixed HTTPS origin "
                    "when LINE_ACCOUNT_LINK_ENABLED=true"
                )
            self.line_account_link_base_url = base_url
        if self.line_daily_notification_enabled:
            if not self.line_account_link_enabled:
                raise ValueError(
                    "LINE_ACCOUNT_LINK_ENABLED must be true when "
                    "LINE_DAILY_NOTIFICATION_ENABLED=true"
                )
            if len(self.line_subject_encryption_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "LINE_SUBJECT_ENCRYPTION_SECRET must contain at least 32 bytes "
                    "when LINE_DAILY_NOTIFICATION_ENABLED=true"
                )
            if self.line_subject_encryption_secret in {
                self.line_channel_secret,
                self.line_identity_hmac_secret,
                self.family_invitation_hmac_secret,
            }:
                raise ValueError(
                    "LINE_SUBJECT_ENCRYPTION_SECRET must be independent from all other secrets"
                )
            if self.line_daily_notification_timezone != "Asia/Taipei":
                raise ValueError("LINE_DAILY_NOTIFICATION_TIMEZONE must be Asia/Taipei")
            if not re.fullmatch(
                r"(?:[01][0-9]|2[0-3]):[0-5][0-9]",
                self.line_daily_notification_send_time,
            ):
                raise ValueError("LINE_DAILY_NOTIFICATION_SEND_TIME must use HH:MM")
            if self.line_daily_notification_send_time != "08:00":
                raise ValueError("LINE_DAILY_NOTIFICATION_SEND_TIME must remain 08:00")
        if self.voice_ticket_enabled and len(self.voice_ticket_hmac_secret.encode("utf-8")) < 32:
            raise ValueError(
                "VOICE_TICKET_HMAC_SECRET must contain at least 32 bytes "
                "when VOICE_TICKET_ENABLED=true"
            )
        return self

    # ─── Secret redaction ────────────────────────────────────────────────────────

    @staticmethod
    def _is_sensitive(field_name: str) -> bool:
        """Return True if the field name contains a sensitive substring."""
        lower = field_name.lower()
        return any(sub in lower for sub in _SENSITIVE_SUBSTRINGS)

    def _redacted_dict(self, **kwargs: Any) -> dict[str, Any]:
        """Return model data with sensitive fields replaced by '***'."""
        data = super().model_dump(**kwargs)
        for field_name in data:
            if self._is_sensitive(field_name):
                data[field_name] = "***"
        return data

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Override to redact sensitive fields."""
        return self._redacted_dict(**kwargs)

    def __repr__(self) -> str:
        redacted = self._redacted_dict()
        pairs = ", ".join(f"{k}={v!r}" for k, v in redacted.items())
        return f"Settings({pairs})"

    def __str__(self) -> str:
        return self.__repr__()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance.

    Uses @lru_cache so the same object is returned on every call within the
    process lifetime.
    """
    return Settings()
