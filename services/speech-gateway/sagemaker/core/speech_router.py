"""Conservative language routing and visible fallbacks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from speech_adapters import ASRAdapter
from speech_contracts import ASRResult, SessionContext


@dataclass(slots=True)
class RouteDecision:
    requested_language: str
    adapter_name: str
    reason: str


class SpeechRouter:
    def __init__(
        self,
        adapters: dict[str, ASRAdapter],
        taigi_winner: str = "taiwan-tongues",
    ):
        self.adapters = adapters
        self.taigi_winner = taigi_winner

    def decide(self, requested_language: str, context: SessionContext) -> RouteDecision:
        language = context.preferred_language or requested_language
        if language in {"zh", "en"}:
            target = f"amazon-{language}"
            reason = "AWS managed primary route"
        elif language == "nan":
            target = self.taigi_winner
            reason = "Frozen Taigi benchmark winner"
        elif language == "hak":
            target = "taiwan-tongues"
            reason = "Validated low-resource Hakka candidate"
        elif language == "mixed-zh-nan":
            target = "taiwan-tongues"
            reason = "Multilingual mixed-speech route"
        else:
            raise ValueError(f"Unsupported requested language: {language}")
        if target not in self.adapters:
            raise LookupError(f"Configured adapter is unavailable: {target}")
        return RouteDecision(language, target, reason)

    def transcribe(
        self, audio: Path, requested_language: str, context: SessionContext
    ) -> tuple[RouteDecision, ASRResult]:
        if not context.consent_to_process_audio:
            raise PermissionError("Audio processing consent is required")
        decision = self.decide(requested_language, context)
        try:
            result = self.adapters[decision.adapter_name].transcribe(
                audio, decision.requested_language, context
            )
        except Exception as exc:
            fallback = self.adapters.get("mock")
            if fallback is None:
                raise
            result = fallback.transcribe(audio, decision.requested_language, context)
            result.fallback_reason = (
                f"{decision.adapter_name} failed; visible fixture fallback: "
                f"{type(exc).__name__}"
            )
        return decision, result
