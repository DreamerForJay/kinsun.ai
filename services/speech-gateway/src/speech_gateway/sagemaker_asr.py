"""SageMaker ASR adapter for Hokkien (nan-TW) and Hakka (hak-TW).

The payload shape is fixed by services/speech-gateway/docs/sagemaker-endpoint-contract.md:

    ContentType: application/octet-stream
    Body: raw PCM bytes (no WAV header)
    CustomAttributes: {"language": "nan-TW"|"hak-TW", "sampleRate": 16000}

and the endpoint answers with ``{"text": ..., "confidence": 0.0}``.

Two details from that contract are load-bearing:

* The body is raw samples, not a WAV file. Sending a WAV header would be decoded
  as audio and transcribed as noise instead of failing loudly.
* ``confidence`` may be missing, in which case it is treated as 0. That reads as
  "unverified" rather than "certain", so a missing score sends the turn to
  confirmation instead of letting it through unchecked.
"""

from __future__ import annotations

import asyncio
import json

import boto3

from speech_gateway.models import SageMakerLanguage, TranscriptSegment

MODEL_VERSION_UNKNOWN = "sagemaker-unknown"


class SageMakerAsrNotConfiguredError(RuntimeError):
    """Raised when no endpoint is configured for a Hokkien/Hakka request."""


async def transcribe_via_sagemaker(
    audio: bytes,
    language: SageMakerLanguage,
    sample_rate: int,
    region: str,
    endpoint_name: str | None,
) -> tuple[str, float, list[TranscriptSegment], str]:
    if not endpoint_name:
        # Fail closed. Falling back to the Mandarin model would return a
        # confident-looking transcript of words the elder did not say.
        raise SageMakerAsrNotConfiguredError(
            "no SageMaker ASR endpoint is configured for this language"
        )

    client = boto3.client("sagemaker-runtime", region_name=region)

    def call() -> dict:
        return client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/octet-stream",
            Body=audio,
            CustomAttributes=json.dumps({"language": language, "sampleRate": sample_rate}),
        )

    response = await asyncio.to_thread(call)

    body = response.get("Body")
    payload = json.loads(body.read().decode("utf-8")) if body is not None else {}
    text = payload.get("text") or ""
    # Absent confidence means unverified, not perfect.
    confidence = float(payload.get("confidence") or 0.0)
    model_version = response.get("CustomAttributes") or MODEL_VERSION_UNKNOWN

    segments = (
        [
            TranscriptSegment(
                text=text,
                start_time=0.0,
                end_time=0.0,
                confidence=confidence,
            )
        ]
        if text
        else []
    )
    return text, confidence, segments, model_version
