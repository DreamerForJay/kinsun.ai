"""Speech gateway: the Transcribe/Polly boundary for the canonical voice path.

Scope is deliberately narrow. This service converts audio to text and text to
audio. It does not store transcripts, evaluate consent, extract events or decide
anything about an elder's care — those belong to Core, which is the only place
allowed to hold formal state.

Consequence worth stating plainly: because nothing here is persisted, a caller
must still go through Core's consent and voice-session gates before acting on a
transcript. This service being reachable is not authorization to record someone.
"""

from __future__ import annotations

import base64
import binascii
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from speech_gateway.asr import MODEL_VERSION, transcribe_pcm
from speech_gateway.models import (
    SynthesizeRequest,
    SynthesizeResponse,
    TranscribeRequest,
    TranscribeResponse,
)
from speech_gateway.sagemaker_asr import (
    SageMakerAsrNotConfiguredError,
    transcribe_via_sagemaker,
)
from speech_gateway.settings import get_settings
from speech_gateway.tts import synthesize

# Language routing is the single place this decision is made, mirroring
# packages/backend/src/asr/routing.ts: Mandarin/English always go to Transcribe,
# Hokkien/Hakka always go to SageMaker. Nothing else should branch on language.
_SAGEMAKER_LANGUAGES = frozenset({"nan-TW", "hak-TW"})

logger = logging.getLogger("speech_gateway")

# Raw audio and transcripts are Restricted Data, so failures are logged by
# category only. No audio bytes and no recognised text reach the log.
MAX_AUDIO_BYTES = 5 * 1024 * 1024


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="kinsun-speech-gateway", version="0.1.0")

    # Local development only: the browser page used for manual voice checks is
    # served from a different port. A deployed gateway must be reached through
    # the BFF, not directly from a browser.
    if settings.APP_ENV == "local":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
            allow_methods=["POST"],
            allow_headers=["content-type"],
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "speech-gateway", "version": "0.1.0"}

    @app.post("/api/v1/speech/transcriptions", response_model=TranscribeResponse)
    async def create_transcription(payload: TranscribeRequest) -> TranscribeResponse:
        try:
            audio = base64.b64decode(payload.audio_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=422, detail="audio_base64 is not valid base64") from exc

        if not audio:
            raise HTTPException(status_code=422, detail="audio payload is empty")
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="audio payload is too large")

        model_version = MODEL_VERSION
        try:
            if payload.language in _SAGEMAKER_LANGUAGES:
                text, confidence, segments, model_version = await transcribe_via_sagemaker(
                    audio,
                    payload.language,  # type: ignore[arg-type]
                    payload.sample_rate,
                    settings.AWS_REGION,
                    settings.SAGEMAKER_ASR_ENDPOINT,
                )
            else:
                text, confidence, segments = await transcribe_pcm(
                    audio,
                    payload.language,  # type: ignore[arg-type]
                    payload.sample_rate,
                    settings.AWS_REGION,
                )
        except SageMakerAsrNotConfiguredError as exc:
            # 501 rather than 502: the language is understood but this deployment
            # has no model for it, which is a different thing for the caller than
            # a model that failed.
            logger.warning("no ASR endpoint configured for %s", payload.language)
            raise HTTPException(
                status_code=501, detail="this language is not available in this deployment"
            ) from exc
        except Exception as exc:
            logger.warning("transcription failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail="speech recognition unavailable") from exc

        return TranscribeResponse(
            text=text,
            confidence=confidence,
            confidence_acceptable=confidence >= settings.ASR_CONFIDENCE_THRESHOLD,
            language=payload.language,
            model_version=model_version,
            segments=segments,
        )

    @app.post("/api/v1/speech/syntheses", response_model=SynthesizeResponse)
    async def create_synthesis(payload: SynthesizeRequest) -> SynthesizeResponse:
        try:
            audio, content_type, voice_id = await synthesize(
                payload.text, payload.language, payload.speaking_speed, settings.AWS_REGION
            )
        except Exception as exc:
            logger.warning("synthesis failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail="speech synthesis unavailable") from exc

        return SynthesizeResponse(
            audio_base64=base64.b64encode(audio).decode("ascii"),
            content_type=content_type,
            voice_id=voice_id,
        )

    return app


app = create_app()
