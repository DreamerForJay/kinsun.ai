from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "speech_workbench.py"
SPEC = importlib.util.spec_from_file_location("speech_workbench", MODULE_PATH)
assert SPEC and SPEC.loader
workbench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workbench)


def test_empty_transcript_always_requires_confirmation() -> None:
    assert workbench.confirmation_required(1.0, "") is True


def test_low_confidence_requires_confirmation() -> None:
    assert workbench.confirmation_required(0.64, "Synthetic transcript") is True


def test_threshold_allows_confirmed_path() -> None:
    assert workbench.confirmation_required(0.65, "Synthetic transcript") is False


def test_agent_call_fails_before_network_when_not_confirmed() -> None:
    with pytest.raises(Exception, match="尚未人工確認"):
        workbench.call_core_agent(
            "Synthetic transcript",
            False,
            "00000000-0000-4000-8000-000000000001",
            "http://127.0.0.1:8000",
            "synthetic-token",
        )


def test_external_tts_rejects_unconfirmed_data_classification() -> None:
    with pytest.raises(Exception, match="Synthetic"):
        workbench.synthesize_external_tts(
            "Synthetic text",
            "台語（nan-TW／SageMaker）",
            False,
            "sixian",
            1.0,
            "model6",
        )


def test_asr_rejects_unapproved_audio_before_conversion() -> None:
    with pytest.raises(Exception, match="Synthetic"):
        workbench.invoke_asr(
            "synthetic.wav",
            "繁體中文（zh-TW／Amazon Transcribe）",
            "kinsun-speech-asr-v1",
            "us-west-2",
            False,
        )


def test_confirmed_transcript_uses_core_companion_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "reply_text": "Synthetic safe reply",
                    "reply_language": "nan-TW",
                    "agent_run_id": "00000000-0000-4000-8000-000000000010",
                    "trace_id": "trace-synthetic",
                    "context_manifest_id": "manifest-synthetic",
                    "result_status": "SUCCESS",
                    "safety_decision": "ALLOW",
                    "risk_level": "LOW",
                    "reason_codes": ["ALLOW"],
                    "model_route": "mock-provider",
                }
            }

    def fake_post(url, *, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(workbench.httpx, "post", fake_post)
    reply, language, metadata = workbench.call_core_agent(
        "Synthetic transcript",
        True,
        "00000000-0000-4000-8000-000000000001",
        "http://127.0.0.1:8000",
        "synthetic-token",
    )

    assert reply == "Synthetic safe reply"
    assert language == "nan-TW"
    assert captured["url"] == (
        "http://127.0.0.1:8000/api/v1/voice-sessions/"
        "00000000-0000-4000-8000-000000000001/companion-turns"
    )
    assert captured["json"] == {"input_text": "Synthetic transcript"}
    assert captured["headers"]["Authorization"] == "Bearer synthetic-token"
    assert metadata["safety_decision"] == "ALLOW"
