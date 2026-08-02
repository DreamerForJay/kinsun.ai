"""Amazon Transcribe streaming adapter.

Ported from packages/backend/src/asr/adapters.ts, which was verified against the
live service. Two details there were learned the hard way and are preserved:

1. Audio must be sent as a sequence of small frames. A single AudioEvent holding
   a whole utterance is rejected outright with
   "Your stream is too big. Reduce the frame size and try your request again."
2. Confidence is the minimum across segments, not the mean, so one poorly
   recognised span still forces a confirmation instead of being averaged away.
"""

from __future__ import annotations

import asyncio

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

from speech_gateway.models import TranscribeLanguage, TranscriptSegment

# 3200 bytes = 100 ms of 16 kHz 16-bit mono PCM. Frame size is a service limit,
# not a tuning knob: larger frames fail the whole request.
AUDIO_FRAME_BYTES = 3200

LANGUAGE_CODES: dict[TranscribeLanguage, str] = {
    "zh-TW": "zh-TW",
    "en-US": "en-US",
}

MODEL_VERSION = "aws-transcribe-streaming"


class _SegmentCollector(TranscriptResultStreamHandler):
    def __init__(self, stream) -> None:  # noqa: ANN001 - SDK type
        super().__init__(stream)
        self.segments: list[TranscriptSegment] = []

    async def handle_transcript_event(self, transcript_event: TranscriptEvent) -> None:
        for result in transcript_event.transcript.results:
            if result.is_partial:
                continue
            alternatives = result.alternatives or []
            if not alternatives:
                continue
            alternative = alternatives[0]
            if not alternative.transcript:
                continue

            items = alternative.items or []
            confidences = [
                item.confidence for item in items if getattr(item, "confidence", None) is not None
            ]
            segment_confidence = sum(confidences) / len(confidences) if confidences else 1.0

            self.segments.append(
                TranscriptSegment(
                    text=alternative.transcript,
                    start_time=result.start_time or 0.0,
                    end_time=result.end_time or 0.0,
                    confidence=segment_confidence,
                )
            )


async def transcribe_pcm(
    audio: bytes,
    language: TranscribeLanguage,
    sample_rate: int,
    region: str,
) -> tuple[str, float, list[TranscriptSegment]]:
    client = TranscribeStreamingClient(region=region)
    stream = await client.start_stream_transcription(
        language_code=LANGUAGE_CODES[language],
        media_sample_rate_hz=sample_rate,
        media_encoding="pcm",
    )

    async def send_frames() -> None:
        for offset in range(0, len(audio), AUDIO_FRAME_BYTES):
            await stream.input_stream.send_audio_event(
                audio_chunk=audio[offset : offset + AUDIO_FRAME_BYTES]
            )
        await stream.input_stream.end_stream()

    collector = _SegmentCollector(stream.output_stream)
    await asyncio.gather(send_frames(), collector.handle_events())

    text = "".join(segment.text for segment in collector.segments)
    confidence = min((s.confidence for s in collector.segments), default=1.0)
    return text, confidence, collector.segments
