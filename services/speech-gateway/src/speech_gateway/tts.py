"""Amazon Polly adapter.

Ported from packages/backend/src/tts/adapters.ts and verified against the live
service with the same voices, engine and SSML shape.
"""

from __future__ import annotations

import asyncio

import boto3

from speech_gateway.models import SpeakingSpeed, TranscribeLanguage

# Zhiyu is Polly's Mandarin neural voice. It is Mainland-accented Mandarin rather
# than Taiwanese-accented; that is a product decision to revisit, not a defect.
VOICE_BY_LANGUAGE: dict[TranscribeLanguage, str] = {
    "zh-TW": "Zhiyu",
    "en-US": "Joanna",
}

SSML_RATE: dict[SpeakingSpeed, str] = {"slow": "80%", "normal": "100%", "fast": "120%"}


def _to_ssml(text: str, speaking_speed: SpeakingSpeed) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<speak><prosody rate="{SSML_RATE[speaking_speed]}">{escaped}</prosody></speak>'


async def synthesize(
    text: str,
    language: TranscribeLanguage,
    speaking_speed: SpeakingSpeed,
    region: str,
) -> tuple[bytes, str, str]:
    voice_id = VOICE_BY_LANGUAGE[language]
    client = boto3.client("polly", region_name=region)

    def call() -> dict:
        return client.synthesize_speech(
            Text=_to_ssml(text, speaking_speed),
            TextType="ssml",
            OutputFormat="mp3",
            VoiceId=voice_id,
            Engine="neural",
        )

    response = await asyncio.to_thread(call)
    stream = response.get("AudioStream")
    if stream is None:
        raise RuntimeError("Polly returned no audio stream")
    return stream.read(), response.get("ContentType", "audio/mpeg"), voice_id
