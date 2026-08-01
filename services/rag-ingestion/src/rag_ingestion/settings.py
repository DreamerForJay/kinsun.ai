"""Configuration loading and staging-only safety guards.

Environment variables override checked-in YAML/JSON configuration.  Optional
fields stay optional until the operation that needs them is invoked, so local
allowlist validation never requires AWS credentials or an OpenSearch endpoint.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

REQUIRED_EMBEDDING_DIMENSION = 1024


class SettingsError(ValueError):
    """Raised when an operation is missing safe, required configuration."""


class IngestionSettings(BaseSettings):
    """RAG ingestion settings sourced from config files and environment."""

    aws_region: str | None = Field(default=None, alias="AWS_REGION")
    bedrock_embedding_model_id: str | None = Field(default=None, alias="BEDROCK_EMBEDDING_MODEL_ID")
    bedrock_embedding_dimension: int = Field(
        default=REQUIRED_EMBEDDING_DIMENSION,
        alias="BEDROCK_EMBEDDING_DIMENSION",
    )
    opensearch_host: str | None = Field(default=None, alias="OPENSEARCH_HOST")
    opensearch_index: str | None = Field(default=None, alias="OPENSEARCH_INDEX")
    opensearch_alias: str | None = Field(default=None, alias="OPENSEARCH_ALIAS")
    rag_allowlist_path: Path | None = Field(default=None, alias="RAG_ALLOWLIST_PATH")
    rag_allowlist_expected_sha256: str | None = Field(
        default=None, alias="RAG_ALLOWLIST_EXPECTED_SHA256"
    )
    rag_require_owner_signature: bool = Field(default=False, alias="RAG_REQUIRE_OWNER_SIGNATURE")
    rag_production_enabled: bool = Field(default=False, alias="RAG_PRODUCTION_ENABLED")
    rag_chunks_dir: Path | None = Field(default=None, alias="RAG_CHUNKS_DIR")
    rag_mode: Literal["staging", "production"] = Field(default="staging", alias="RAG_MODE")
    rag_embeddings_path: Path | None = Field(default=None, alias="RAG_EMBEDDINGS_PATH")
    rag_receipt_path: Path | None = Field(default=None, alias="RAG_RECEIPT_PATH")
    rag_embedding_config_path: Path | None = Field(default=None, alias="RAG_EMBEDDING_CONFIG_PATH")
    rag_opensearch_index_config_path: Path | None = Field(
        default=None, alias="RAG_OPENSEARCH_INDEX_CONFIG_PATH"
    )
    rag_hybrid_natural_config_path: Path | None = Field(
        default=None, alias="RAG_HYBRID_NATURAL_CONFIG_PATH"
    )
    rag_hybrid_legal_config_path: Path | None = Field(
        default=None, alias="RAG_HYBRID_LEGAL_CONFIG_PATH"
    )
    rag_staging_filters_config_path: Path | None = Field(
        default=None, alias="RAG_STAGING_FILTERS_CONFIG_PATH"
    )
    rag_smoke_config_path: Path | None = Field(default=None, alias="RAG_SMOKE_CONFIG_PATH")
    agent_runtime_base_url: str | None = Field(default=None, alias="AGENT_RUNTIME_BASE_URL")
    embedding_batch_size: int = 96
    embedding_truncate: str = "NONE"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: EnvSettingsSource,
        dotenv_settings: DotEnvSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Environment and .env override checked-in config passed as init values."""

        return env_settings, dotenv_settings, init_settings, file_secret_settings

    @field_validator("bedrock_embedding_dimension")
    @classmethod
    def dimension_must_be_1024(cls, value: int) -> int:
        if value != REQUIRED_EMBEDDING_DIMENSION:
            raise ValueError(f"embedding dimension must be {REQUIRED_EMBEDDING_DIMENSION}")
        return value

    @field_validator("embedding_batch_size")
    @classmethod
    def batch_size_must_fit_cohere_limit(cls, value: int) -> int:
        if not 1 <= value <= 96:
            raise ValueError("embedding batch size must be between 1 and 96")
        return value

    @field_validator("embedding_truncate")
    @classmethod
    def validate_truncate(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"NONE", "LEFT", "RIGHT"}:
            raise ValueError("embedding truncate must be NONE, LEFT, or RIGHT")
        return normalized

    @field_validator("opensearch_host")
    @classmethod
    def host_must_not_contain_credentials(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parsed = urlsplit(value if "://" in value else f"https://{value}")
        if parsed.username or parsed.password:
            raise ValueError("OPENSEARCH_HOST must not contain credentials")
        return value.rstrip("/")

    @field_validator("opensearch_index", "opensearch_alias")
    @classmethod
    def index_names_must_be_staging(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.casefold()
        if "staging" not in normalized or "production" in normalized or "prod" in normalized:
            raise ValueError("OpenSearch index and alias names must be explicitly staging")
        return value

    def require_paths(self) -> tuple[Path, Path]:
        if self.rag_allowlist_path is None or self.rag_chunks_dir is None:
            raise SettingsError("RAG_ALLOWLIST_PATH and RAG_CHUNKS_DIR are required")
        if "pending-revalidation" in {
            part.casefold() for part in self.rag_chunks_dir.resolve().parts
        }:
            raise SettingsError("pending-revalidation is never a valid ingestion source")
        return self.rag_allowlist_path, self.rag_chunks_dir

    def require_bedrock(self) -> tuple[str, str, int]:
        missing = [
            name
            for name, value in (
                ("AWS_REGION", self.aws_region),
                ("BEDROCK_EMBEDDING_MODEL_ID", self.bedrock_embedding_model_id),
            )
            if not value
        ]
        if missing:
            raise SettingsError(f"missing Bedrock settings: {', '.join(missing)}")
        return (
            str(self.aws_region),
            str(self.bedrock_embedding_model_id),
            self.bedrock_embedding_dimension,
        )

    def require_opensearch(self) -> tuple[str, str, str, str]:
        missing = [
            name
            for name, value in (
                ("AWS_REGION", self.aws_region),
                ("OPENSEARCH_HOST", self.opensearch_host),
                ("OPENSEARCH_INDEX", self.opensearch_index),
                ("OPENSEARCH_ALIAS", self.opensearch_alias),
            )
            if not value
        ]
        if missing:
            raise SettingsError(f"missing OpenSearch settings: {', '.join(missing)}")
        return (
            str(self.aws_region),
            str(self.opensearch_host),
            str(self.opensearch_index),
            str(self.opensearch_alias),
        )

    def require_agent_runtime_base_url(self) -> str:
        if self.agent_runtime_base_url is None or not self.agent_runtime_base_url.strip():
            raise SettingsError("AGENT_RUNTIME_BASE_URL is required for the end-to-end smoke test")
        value = self.agent_runtime_base_url.strip()
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise SettingsError("AGENT_RUNTIME_BASE_URL must be an HTTP(S) origin")
        return value.rstrip("/")

    def assert_staging_only_external_execution(self) -> None:
        """Keep this first release from targeting a production environment."""

        if self.rag_mode != "staging" or self.rag_production_enabled:
            raise SettingsError("this ingestion service release can only execute staging targets")

    def embedding_artifact_path(self, repository_root: Path) -> Path:
        path = self.rag_embeddings_path or default_embedding_artifact_path()
        return ensure_artifact_outside_repository(path, repository_root)


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw) if path.suffix.casefold() == ".json" else yaml.safe_load(raw)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SettingsError(f"cannot read configuration {path}: {type(exc).__name__}") from exc
    if not isinstance(parsed, dict):
        raise SettingsError(f"configuration root must be an object: {path}")
    return parsed


def load_settings(
    *,
    embedding_config_path: Path,
    index_config_path: Path,
    staging_config_path: Path,
    repository_root: Path,
    environ: dict[str, str] | None = None,
) -> IngestionSettings:
    """Load checked-in config, with environment taking precedence."""

    embedding_config = _read_mapping(embedding_config_path)
    index_config = _read_mapping(index_config_path)
    staging_config = _read_mapping(staging_config_path)

    embedding = embedding_config.get("embedding", {})
    index = index_config.get("index", {})
    paths = staging_config.get("paths", {})
    if not all(isinstance(value, dict) for value in (embedding, index, paths)):
        raise SettingsError("embedding, index, and paths configuration must be objects")

    values: dict[str, Any] = {
        "BEDROCK_EMBEDDING_MODEL_ID": embedding.get("model_id"),
        "BEDROCK_EMBEDDING_DIMENSION": embedding.get("dimension", REQUIRED_EMBEDDING_DIMENSION),
        "AWS_REGION": embedding.get("region"),
        "OPENSEARCH_INDEX": index.get("name"),
        "OPENSEARCH_ALIAS": index.get("alias"),
        "RAG_MODE": staging_config.get("mode", index_config.get("mode")),
        "RAG_ALLOWLIST_PATH": _resolve_repo_path(paths.get("allowlist"), repository_root),
        "RAG_CHUNKS_DIR": _resolve_repo_path(paths.get("chunks_dir"), repository_root),
        "embedding_batch_size": embedding.get("batch_size", 96),
        "embedding_truncate": embedding.get("truncate", "NONE"),
    }
    environment = dict(os.environ if environ is None else environ)
    for alias in (
        "AWS_REGION",
        "BEDROCK_EMBEDDING_MODEL_ID",
        "BEDROCK_EMBEDDING_DIMENSION",
        "OPENSEARCH_HOST",
        "OPENSEARCH_INDEX",
        "OPENSEARCH_ALIAS",
        "RAG_ALLOWLIST_PATH",
        "RAG_ALLOWLIST_EXPECTED_SHA256",
        "RAG_REQUIRE_OWNER_SIGNATURE",
        "RAG_PRODUCTION_ENABLED",
        "RAG_CHUNKS_DIR",
        "RAG_MODE",
        "RAG_EMBEDDINGS_PATH",
        "RAG_RECEIPT_PATH",
        "RAG_EMBEDDING_CONFIG_PATH",
        "RAG_OPENSEARCH_INDEX_CONFIG_PATH",
        "RAG_HYBRID_NATURAL_CONFIG_PATH",
        "RAG_HYBRID_LEGAL_CONFIG_PATH",
        "RAG_STAGING_FILTERS_CONFIG_PATH",
        "RAG_SMOKE_CONFIG_PATH",
        "AGENT_RUNTIME_BASE_URL",
    ):
        if environment.get(alias):
            values[alias] = environment[alias]
    values = {key: value for key, value in values.items() if value is not None}
    return IngestionSettings(**values)


def _resolve_repo_path(value: Any, repository_root: Path) -> Path | None:
    if value is None:
        return None
    path = Path(str(value))
    return path if path.is_absolute() else repository_root / path


def default_embedding_artifact_path() -> Path:
    return Path(tempfile.gettempdir()) / "kinsun-rag" / "embeddings.jsonl"


def ensure_artifact_outside_repository(path: Path, repository_root: Path) -> Path:
    resolved_path = path.expanduser().resolve()
    resolved_root = repository_root.expanduser().resolve()
    if resolved_path == resolved_root or resolved_root in resolved_path.parents:
        raise SettingsError("embedding artifacts must never be written inside the repository")
    return resolved_path
