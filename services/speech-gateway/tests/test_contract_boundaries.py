"""Boundary tests for the speech gateway.

These use FastAPI's TestClient with the AWS calls patched out: what is asserted
here is the contract shape and the refusals, not Transcribe/Polly behaviour.
The live round trip is verified separately against the real services.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from speech_gateway.app import create_app
from speech_gateway.models import TranscriptSegment
from speech_gateway.settings import get_settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def fake_transcribe(audio, language, sample_rate, region):  # noqa: ANN001, ARG001
        return (
            "阿嬤您好",
            0.81,
            [TranscriptSegment(text="阿嬤您好", start_time=0.0, end_time=1.0, confidence=0.81)],
        )

    async def fake_synthesize(text, language, speaking_speed, region):  # noqa: ANN001, ARG001
        return b"fake-mp3-bytes", "audio/mpeg", "Zhiyu"

    monkeypatch.setattr("speech_gateway.app.transcribe_pcm", fake_transcribe)
    monkeypatch.setattr("speech_gateway.app.synthesize", fake_synthesize)
    return TestClient(create_app())


def _audio(payload: bytes = b"\x00\x01" * 800) -> str:
    return base64.b64encode(payload).decode("ascii")


def test_transcription_returns_transcript_and_confidence(client: TestClient) -> None:
    response = client.post(
        "/api/v1/speech/transcriptions",
        json={"audio_base64": _audio(), "language": "zh-TW", "sample_rate": 16000},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "阿嬤您好"
    assert body["confidence_acceptable"] is True


def test_low_confidence_is_reported_as_not_acceptable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Below the threshold the caller must ask the elder to repeat.

    The gateway still returns the text so the caller can show a confirmation
    prompt, but it must not claim the transcript is usable.
    """

    async def low_confidence(audio, language, sample_rate, region):  # noqa: ANN001, ARG001
        return ("聽不清楚", 0.42, [])

    monkeypatch.setattr("speech_gateway.app.transcribe_pcm", low_confidence)

    response = client.post(
        "/api/v1/speech/transcriptions",
        json={"audio_base64": _audio(), "language": "zh-TW"},
    )
    assert response.status_code == 200
    assert response.json()["confidence_acceptable"] is False


@pytest.mark.parametrize("language", ["nan-TW", "hak-TW"])
def test_hokkien_and_hakka_without_an_endpoint_are_refused_not_answered_in_mandarin(
    client: TestClient, language: str
) -> None:
    """With no SageMaker endpoint configured these must fail, not fall back.

    Falling through to Transcribe would return a fluent Mandarin transcript of
    words the elder never said. 501 rather than 502 because the request is valid
    and understood — this deployment simply has no model for that language.
    """

    response = client.post(
        "/api/v1/speech/transcriptions",
        json={"audio_base64": _audio(), "language": language},
    )
    assert response.status_code == 501


@pytest.mark.parametrize("language", ["nan-TW", "hak-TW"])
def test_hokkien_and_hakka_route_to_sagemaker_when_configured(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    """The Mandarin path must not be reachable for these languages."""

    called: dict[str, object] = {}

    async def fake_sagemaker(audio, lang, sample_rate, region, endpoint_name):  # noqa: ANN001, ARG001
        called["language"] = lang
        called["endpoint"] = endpoint_name
        return ("汝食飽未", 0.72, [], "kinsun-asr-v1")

    async def unreachable_transcribe(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise AssertionError("Transcribe must not be used for nan-TW/hak-TW")

    monkeypatch.setenv("SAGEMAKER_ASR_ENDPOINT", "kinsun-speech-asr-v1")
    get_settings.cache_clear()
    monkeypatch.setattr("speech_gateway.app.transcribe_via_sagemaker", fake_sagemaker)
    monkeypatch.setattr("speech_gateway.app.transcribe_pcm", unreachable_transcribe)

    try:
        response = TestClient(create_app()).post(
            "/api/v1/speech/transcriptions",
            json={"audio_base64": _audio(), "language": language},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "汝食飽未"
    assert body["model_version"] == "kinsun-asr-v1"
    assert called == {"language": language, "endpoint": "kinsun-speech-asr-v1"}


def test_missing_sagemaker_confidence_is_treated_as_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 0.0 score must send the turn to confirmation, not through unchecked."""

    async def zero_confidence(audio, lang, sample_rate, region, endpoint_name):  # noqa: ANN001, ARG001
        return ("汝食飽未", 0.0, [], "kinsun-asr-v1")

    monkeypatch.setenv("SAGEMAKER_ASR_ENDPOINT", "kinsun-speech-asr-v1")
    get_settings.cache_clear()
    monkeypatch.setattr("speech_gateway.app.transcribe_via_sagemaker", zero_confidence)

    try:
        response = TestClient(create_app()).post(
            "/api/v1/speech/transcriptions",
            json={"audio_base64": _audio(), "language": "nan-TW"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["confidence_acceptable"] is False


@pytest.mark.parametrize("language", ["nan-TW", "hak-TW"])
def test_synthesis_still_refuses_hokkien_and_hakka(client: TestClient, language: str) -> None:
    """No Hokkien/Hakka TTS endpoint is deployed, so this stays a hard refusal."""

    response = client.post(
        "/api/v1/speech/syntheses",
        json={"text": "汝食飽未", "language": language},
    )
    assert response.status_code == 422


def test_invalid_base64_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/speech/transcriptions",
        json={"audio_base64": "!!!not base64!!!", "language": "zh-TW"},
    )
    assert response.status_code == 422


def test_empty_audio_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/speech/transcriptions",
        json={"audio_base64": "", "language": "zh-TW"},
    )
    assert response.status_code == 422


def test_unexpected_field_is_refused(client: TestClient) -> None:
    """extra="forbid" keeps the contract able to catch a typo'd field."""

    response = client.post(
        "/api/v1/speech/syntheses",
        json={"text": "測試", "language": "zh-TW", "speed": "fast"},
    )
    assert response.status_code == 422


def test_synthesis_returns_base64_audio(client: TestClient) -> None:
    response = client.post(
        "/api/v1/speech/syntheses",
        json={"text": "測試", "language": "zh-TW", "speaking_speed": "slow"},
    )
    assert response.status_code == 200
    body = response.json()
    assert base64.b64decode(body["audio_base64"]) == b"fake-mp3-bytes"
    assert body["voice_id"] == "Zhiyu"


def test_upstream_failure_becomes_502_without_leaking_details(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(text, language, speaking_speed, region):  # noqa: ANN001, ARG001
        raise RuntimeError("bucket=secret-internal-name token=abc123")

    monkeypatch.setattr("speech_gateway.app.synthesize", boom)

    response = client.post(
        "/api/v1/speech/syntheses",
        json={"text": "測試", "language": "zh-TW"},
    )
    assert response.status_code == 502
    assert "secret-internal-name" not in response.text
    assert "abc123" not in response.text
