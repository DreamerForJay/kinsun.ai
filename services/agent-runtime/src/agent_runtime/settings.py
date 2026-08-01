from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    MODEL_PROVIDER: str = "mock"
    MAX_AGENT_DECISIONS: int = 3
    MAX_TOOL_ROUNDS: int = 2
    MAX_TOTAL_TOOLS: int = 5
    MAX_REWRITE: int = 1
    DEFAULT_LANGUAGE: str = "zh-TW"
    API_VERSION: str = "1.0.0"
    AGENT_VERSION: str = "0.0.1"
    CORE_API_BASE_URL: AnyHttpUrl | None = None
    CORE_API_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=30)
    RAG_MODE: str = "disabled"
    RAG_EMBEDDING_CONFIG_PATH: str = "config/rag/embedding.yaml"
    RAG_OPENSEARCH_INDEX_CONFIG_PATH: str = "config/rag/opensearch-index-v1.json"
    RAG_HYBRID_NATURAL_CONFIG_PATH: str = "config/rag/hybrid-natural-language.json"
    RAG_HYBRID_LEGAL_CONFIG_PATH: str = "config/rag/hybrid-legal.json"
    AWS_REGION: str | None = None
    BEDROCK_EMBEDDING_MODEL_ID: str | None = None
    BEDROCK_EMBEDDING_DIMENSION: int = 1024
    OPENSEARCH_HOST: str | None = None
    OPENSEARCH_INDEX: str | None = None
    OPENSEARCH_ALIAS: str | None = None

    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[4] / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
