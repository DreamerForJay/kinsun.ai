from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Mandarin and English go to Amazon Transcribe.
TranscribeLanguage = Literal["zh-TW", "en-US"]

# Hokkien and Hakka go to a self-hosted SageMaker endpoint. Sending them to a
# Mandarin model instead would transcribe Taiwanese speech with the wrong model
# and report the result as if it had been understood.
SageMakerLanguage = Literal["nan-TW", "hak-TW"]

SpeechLanguage = Literal["zh-TW", "en-US", "nan-TW", "hak-TW"]
SpeakingSpeed = Literal["slow", "normal", "fast"]


class GatewayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TranscribeRequest(GatewayModel):
    """Audio is base64 so the boundary stays a plain JSON contract."""

    audio_base64: str = Field(min_length=1)
    language: SpeechLanguage
    # 16 kHz mono PCM is what the browser recorder produces and what Transcribe
    # expects; the field is explicit because a mismatch yields silent garbage
    # rather than an error.
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    encoding: Literal["pcm"] = "pcm"


class TranscriptSegment(GatewayModel):
    text: str
    start_time: float
    end_time: float
    confidence: float


class TranscribeResponse(GatewayModel):
    text: str
    # Minimum across segments, matching the legacy implementation: one badly
    # recognised span should not be averaged away by confident ones.
    confidence: float
    # False means the caller must ask the elder to repeat rather than act on
    # `text`. The threshold lives in settings, not in the client.
    confidence_acceptable: bool
    language: SpeechLanguage
    model_version: str
    segments: list[TranscriptSegment]


class SynthesizeRequest(GatewayModel):
    text: str = Field(min_length=1, max_length=3000)
    # TTS still covers Mandarin and English only: no Hokkien/Hakka synthesis
    # endpoint is deployed yet, and the contract notes a known crash in the nan
    # TTS model with Han-character input.
    language: TranscribeLanguage
    speaking_speed: SpeakingSpeed = "normal"


class SynthesizeResponse(GatewayModel):
    audio_base64: str
    content_type: str
    voice_id: str
