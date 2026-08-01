#!/usr/bin/env python3
"""SageMaker BYOC real-time inference server for nan-TW/hak-TW ASR.

Wraps the ASR PoC repo's `core/speech_adapters.TransformersASRAdapter`
(Taiwan-Tongues, the best nan/hak candidate found so far -- see
`docs/model-selection.md` for the CER numbers and caveats) behind the exact
HTTP contract `packages/backend/src/asr/adapters.ts`'s `SageMakerAdapter`
already expects (see `docs/sagemaker-endpoint-contract.md`).

This is a from-scratch container (not a SageMaker framework/script-mode
image), so it implements the SageMaker hosting HTTP contract directly:
GET /ping for health checks, POST /invocations for inference, listening on
port 8080. `CustomAttributes` from the backend's InvokeEndpointCommand call
arrives as the `X-Amzn-SageMaker-Custom-Attributes` request header.

Deployment status (2026-08-02): Dockerfile.asr was pushed to the private
competition ECR and invoked through `kinsun-speech-asr-v1` with Synthetic PCM.
This proves deployment and wire compatibility, not ASR quality.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

CORE_DIR = Path(__file__).parent / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from flask import Flask, Response, request  # noqa: E402

# SageMaker-side locale codes (packages/backend's ConcreteLanguage) -> this
# project's internal bare language codes (core/speech_contracts.py etc.).
# Only nan/hak ever reach this endpoint -- zh-TW/en-US are routed to AWS
# Transcribe directly by packages/backend/src/asr/routing.ts and never hit
# SageMaker at all.
LANGUAGE_MAP = {"nan-TW": "nan", "hak-TW": "hak"}

app = Flask(__name__)
_adapter: Any = None
_session_context: Any = None


def _get_adapter() -> tuple[Any, Any]:
    global _adapter, _session_context
    if _adapter is None:
        from speech_adapters import CTranslate2ASRAdapter
        from speech_contracts import SessionContext

        # Endpoint 使用較適合推論部署的 CTranslate2 版本。模型在 image build
        # 階段下載到固定路徑，因此啟動時不需要連線 Hugging Face。
        model_id = os.environ.get(
            "KINSUN_ASR_MODEL_ID", "adi-gov-tw/Taiwan-Tongues-ASR-CE-v2.0"
        )
        model_revision = os.environ.get("KINSUN_ASR_MODEL_REVISION", "unknown")
        _adapter = CTranslate2ASRAdapter(
            model_id=os.environ.get("KINSUN_ASR_MODEL_PATH", model_id),
            device=os.environ.get("KINSUN_ASR_DEVICE", "cuda"),
            compute_type=os.environ.get("KINSUN_ASR_COMPUTE_TYPE", "float16"),
            model_version=f"{model_id}@{model_revision}",
        )
        # SessionContext exists for voice_server.py's multi-turn conversation
        # tracking (consent, preferred language, entity confirmation). A
        # SageMaker invocation is a single stateless request, so this is a
        # minimal stand-in, not a real session.
        _session_context = SessionContext(
            session_id="sagemaker-invocation",
            elder_id="unknown",
            consent_to_process_audio=True,
        )
    return _adapter, _session_context


def _pcm_bytes_to_wav_path(pcm_bytes: bytes, sample_rate: int) -> Path:
    """Wrap raw 16-bit mono PCM bytes in a WAV container.

    The existing adapters take a file `Path` (built for voice_server.py's
    file-upload flow), not raw streaming bytes -- this is the one real
    format conversion this container adds on top of the PoC's existing code.
    Only PCM is handled; the wire contract also allows 'opus', but nothing
    in this project currently decodes opus, so an opus request must fail
    loudly here rather than being silently mishandled.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit PCM, matches AudioInput's implicit format
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return Path(tmp.name)


def transcribe_bytes(pcm_bytes: bytes, language: str, sample_rate: int) -> dict[str, Any]:
    """Core logic, factored out of the Flask route so it can be dry-run
    locally (no HTTP, no SageMaker) against real sample audio for
    verification. See ../docs/sagemaker-endpoint-contract.md for the
    response shape this must produce.
    """
    adapter, context = _get_adapter()
    audio_path = _pcm_bytes_to_wav_path(pcm_bytes, sample_rate)
    try:
        result = adapter.transcribe(audio_path, language, context)
    finally:
        audio_path.unlink(missing_ok=True)
    return {"text": result.transcript, "confidence": result.confidence or 0.0}


@app.get("/ping")
def ping() -> Response:
    return Response(status=200)


@app.post("/invocations")
def invocations() -> Response:
    try:
        custom_attributes = json.loads(
            request.headers.get("X-Amzn-SageMaker-Custom-Attributes", "{}")
        )
    except json.JSONDecodeError:
        return Response(
            json.dumps({"error": "CustomAttributes header is not valid JSON"}),
            status=400, mimetype="application/json",
        )
    language = LANGUAGE_MAP.get(custom_attributes.get("language", ""))
    if language is None:
        return Response(
            json.dumps({"error": f"unsupported language {custom_attributes.get('language')!r}"}),
            status=400, mimetype="application/json",
        )
    if request.content_type != "application/octet-stream":
        return Response(
            json.dumps({
                "error": f"unsupported content type {request.content_type!r}, "
                         "expected application/octet-stream",
            }),
            status=415, mimetype="application/json",
        )
    sample_rate = int(custom_attributes.get("sampleRate", 16000))
    payload = transcribe_bytes(request.get_data(), language, sample_rate)
    response = Response(
        json.dumps(payload, ensure_ascii=False), mimetype="application/json"
    )
    # SageMaker Runtime 會把這個 header 對應回 InvokeEndpoint 的
    # CustomAttributes，backend 因而能保存實際模型版本，而不是 unknown。
    adapter, _ = _get_adapter()
    response.headers["X-Amzn-SageMaker-Custom-Attributes"] = adapter.model_version
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
