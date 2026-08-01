"""Application configuration management.

Loads settings from environment variables (and .env file in development mode).
Provides a singleton accessor via get_settings().
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    """Application environment profiles."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


# Determine env_file BEFORE class body evaluation.
# In production we never read .env; in development we do (env vars still take precedence).
_env_file: str | None = ".env" if os.getenv("APP_ENV", "development") != "production" else None

# Substrings in field names that indicate sensitive data (used for redaction).
_SENSITIVE_SUBSTRINGS: tuple[str, ...] = ("password", "secret", "key")


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
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)

    # ─── Testing ─────────────────────────────────────────────────────────────────
    test_database_url: str = ""

    # ─── Secrets (redacted in output) ────────────────────────────────────────────
    database_password: str = ""

    # ─── Authentication ──────────────────────────────────────────────────────────
    fake_auth_enabled: bool = False
    fake_auth_actor_id: UUID | None = None
    fake_auth_tenant_id: UUID | None = None
    fake_auth_actor_role: str = Field(default="ELDER", min_length=1, max_length=64)

    # ─── Internal service adapters ───────────────────────────────────────────────
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
