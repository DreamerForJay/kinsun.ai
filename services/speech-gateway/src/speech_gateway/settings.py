from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    APP_ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    AWS_REGION: str = "us-west-2"

    # Hokkien (nan-TW) and Hakka (hak-TW) ASR run on a self-hosted SageMaker
    # endpoint. When unset, those languages are refused rather than answered by
    # the Mandarin model, which would put words in an elder's mouth.
    SAGEMAKER_ASR_ENDPOINT: str | None = None
    # No Hokkien/Hakka synthesis endpoint is deployed yet.
    SAGEMAKER_TTS_ENDPOINT: str | None = None

    # Kept equal to packages/backend/src/asr/confidence.ts. Below this the caller
    # must ask the elder to repeat instead of acting on the transcript.
    ASR_CONFIDENCE_THRESHOLD: float = 0.6

    model_config = SettingsConfigDict(
        env_file=(SERVICE_ENV_FILE,),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
