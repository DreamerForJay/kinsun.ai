from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_RUNTIME_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


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

    model_config = SettingsConfigDict(
        env_file=AGENT_RUNTIME_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
