#!/usr/bin/env python3
"""SageMaker BYOC real-time inference server for nan-TW/hak-TW TTS.

Wraps the ASR/TTS PoC repo's `core/speech_adapters.MmsTTSAdapter` (nan) and
`VoxHakkaAdapter` (hak, the recommended provider -- see
`docs/model-selection.md`) behind the exact HTTP contract
`packages/backend/src/tts/adapters.ts`'s `SageMakerTtsAdapter` already
expects (see `docs/sagemaker-endpoint-contract.md`).

Same from-scratch BYOC HTTP contract as inference_asr.py: GET /ping, POST
/invocations, port 8080. No CustomAttributes here -- the TTS wire contract
puts everything in the JSON body.

Deployment status (2026-08-02): this TTS server remains a local/container
candidate and has NOT been deployed to SageMaker. Model-license approval and a
fixed offline model revision are still required before creating an endpoint.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

CORE_DIR = Path(__file__).parent / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from flask import Flask, Response, request  # noqa: E402

LANGUAGE_MAP = {"nan-TW": "nan", "hak-TW": "hak"}

# Matches packages/backend/src/tts/adapters.ts's PollyAdapter SSML_RATE
# mapping (80%/100%/120%) so "slow"/"normal"/"fast" means the same thing
# across every language in the pipeline, not just the AWS-native ones.
SPEED_MAP = {"slow": 0.8, "normal": 1.0, "fast": 1.2}

# This container is Linux-based; VoxHakkaAdapter's default venv_python path
# (local_poc/.venv-voxhakka/Scripts/python.exe) is a Windows venv layout and
# does not exist here, so the container-specific path below is passed
# explicitly rather than patching the shared adapter code (kept identical to
# the PoC repo's copy -- see ./core/README in this directory, or the PoC
# repo's core/speech_adapters.py directly).
VOXHAKKA_VENV_PYTHON = Path(__file__).parent / ".venv-voxhakka" / "bin" / "python"

app = Flask(__name__)
_adapters: dict[str, Any] = {}


def _get_adapter(language: str) -> Any:
    if language not in _adapters:
        if language == "nan":
            from speech_adapters import MmsTTSAdapter
            _adapters[language] = MmsTTSAdapter()
        elif language == "hak":
            from speech_adapters import VoxHakkaAdapter
            _adapters[language] = VoxHakkaAdapter(venv_python=VOXHAKKA_VENV_PYTHON)
    return _adapters[language]


def synthesize_bytes(text: str, language: str, speaking_speed: str) -> bytes:
    """Core logic, factored out of the Flask route so it can be dry-run
    locally against sample text (VoxHakka's sixian/hailu dialects; nan Han
    text is romanized to Tai-lo via taibun inside MmsTTSAdapter as of
    2026-08-02, so it now produces audio instead of raising -- see
    docs/model-selection.md).

    Deliberately does NOT catch adapter exceptions: packages/backend/src/tts/
    types.ts's TtsOutcome already treats a failed/thrown SageMaker invocation
    as an expected "degrade to text" case, so there is no need to duplicate
    that fallback logic on this side of the contract.
    """
    speed = SPEED_MAP.get(speaking_speed, 1.0)
    adapter = _get_adapter(language)
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "output.wav"
        result = adapter.synthesize(text, language, voice="", speed=speed, output=output_path)
        return Path(result.audio_stream_or_url).read_bytes()


@app.get("/ping")
def ping() -> Response:
    return Response(status=200)


@app.post("/invocations")
def invocations() -> Response:
    payload = request.get_json(force=True, silent=True)
    if payload is None:
        return Response(
            json.dumps({"error": "request body is not valid JSON"}),
            status=400, mimetype="application/json",
        )
    language = LANGUAGE_MAP.get(payload.get("language", ""))
    text = (payload.get("text") or "").strip()
    if language is None:
        return Response(
            json.dumps({"error": f"unsupported language {payload.get('language')!r}"}),
            status=400, mimetype="application/json",
        )
    if not text:
        return Response(
            json.dumps({"error": "text is required"}), status=400, mimetype="application/json",
        )
    speaking_speed = payload.get("speakingSpeed", "normal")
    audio_bytes = synthesize_bytes(text, language, speaking_speed)
    return Response(audio_bytes, mimetype="audio/wav")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
