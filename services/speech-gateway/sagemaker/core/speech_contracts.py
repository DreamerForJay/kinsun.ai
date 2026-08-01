"""Provider-neutral contracts for the four-language speech PoC."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class LanguageSegment:
    language: str
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(slots=True)
class WordTimestamp:
    word: str
    start_seconds: float
    end_seconds: float
    confidence: float | None = None


@dataclass(slots=True)
class ASRResult:
    transcript: str
    normalized_transcript: str
    detected_language: str
    language_segments: list[LanguageSegment] = field(default_factory=list)
    confidence: float | None = None
    key_entities: list[str] = field(default_factory=list)
    word_timestamps: list[WordTimestamp] = field(default_factory=list)
    provider: str = ""
    model_id: str = ""
    model_version: str = ""
    latency_ms: float = 0.0
    realtime_factor: float | None = None
    needs_confirmation: bool = False
    fallback_reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TTSResult:
    audio_stream_or_url: str | None
    provider: str
    model_id: str
    voice: str
    language: str
    sample_rate: int
    first_audio_latency_ms: float
    total_latency_ms: float
    realtime_factor: float | None
    is_live_generated: bool
    fallback_reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SessionContext:
    session_id: str
    elder_id: str
    preferred_language: str | None = None
    consent_to_process_audio: bool = False
    scenario: str = "quiet"
    key_entities: list[str] = field(default_factory=list)
