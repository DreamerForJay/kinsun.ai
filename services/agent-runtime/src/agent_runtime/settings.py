from functools import lru_cache

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
