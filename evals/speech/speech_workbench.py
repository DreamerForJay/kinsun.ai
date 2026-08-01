#!/usr/bin/env python3
"""成員 D 的本機 Speech 整合工作台。

流程遵守 Gate 1：ASR 低信心必須先人工確認，確認後才能送到 Core API；
Core 再負責 Authorization／Consent 並呼叫 Agent Runtime（含受控 RAG）。
本工具只綁定 127.0.0.1，不提供公開分享，也不保存 Bearer Token。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import boto3
import gradio as gr
import httpx
from gradio_client import Client

DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
DEFAULT_ASR_ENDPOINT = os.getenv("KINSUN_ASR_ENDPOINT", "kinsun-speech-asr-v1")
DEFAULT_TTS_ENDPOINT = os.getenv("KINSUN_TTS_ENDPOINT", "kinsun-speech-tts-v1")
DEFAULT_CORE_URL = os.getenv("KINSUN_CORE_API_URL", "http://127.0.0.1:8000")
LANGUAGES = {"台語（nan-TW）": "nan-TW", "客語（hak-TW）": "hak-TW"}
CONFIDENCE_THRESHOLD = float(os.getenv("KINSUN_ASR_CONFIRM_THRESHOLD", "0.65"))
HAKKA_DIALECTS = ["sixian", "hailu", "dapu", "raoping", "zhaoan", "nansixian"]


def confirmation_required(confidence: float, transcript: str) -> bool:
    """空結果或低於門檻都必須確認；不得用語意看似合理取代 ASR 證據。"""
    return not transcript.strip() or confidence < CONFIDENCE_THRESHOLD


def _pcm_from_audio(audio_path: str) -> bytes:
    """用 ffmpeg 將 Gradio 上傳／錄音統一為 16 kHz、mono、signed 16-bit PCM。"""
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        audio_path,
        "-f",
        "s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
        "pipe:1",
    ]
    completed = subprocess.run(command, check=True, capture_output=True)
    if not completed.stdout:
        raise ValueError("音訊轉換後沒有樣本")
    return completed.stdout


def invoke_sagemaker_asr(
    audio_path: str | None, language_label: str, endpoint_name: str, region: str
) -> tuple[str, float, str, dict[str, Any]]:
    if not audio_path:
        raise gr.Error("請先錄音或上傳 Synthetic／已去識別音訊。")
    language = LANGUAGES[language_label]
    started = time.perf_counter()
    try:
        response = boto3.client(
            "sagemaker-runtime", region_name=region
        ).invoke_endpoint(
            EndpointName=endpoint_name.strip(),
            ContentType="application/octet-stream",
            CustomAttributes=json.dumps({"language": language, "sampleRate": 16000}),
            Body=_pcm_from_audio(audio_path),
        )
        payload = json.loads(response["Body"].read())
    except Exception as exc:
        raise gr.Error(f"SageMaker ASR 呼叫失敗：{type(exc).__name__}") from exc

    transcript = str(payload.get("text", "")).strip()
    confidence = float(payload.get("confidence", 0.0))
    needs_confirmation = confirmation_required(confidence, transcript)
    status = (
        "需要人工確認：請修改逐字稿後勾選『我已確認』。"
        if needs_confirmation
        else "信心值達門檻；仍可人工修正後再送出。"
    )
    metadata = {
        "provider": "aws-sagemaker",
        "endpoint": endpoint_name.strip(),
        "language": language,
        "confidence": confidence,
        "confirmation_threshold": CONFIDENCE_THRESHOLD,
        "needs_confirmation": needs_confirmation,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "model_version": response.get("CustomAttributes"),
    }
    return transcript, confidence, status, metadata


def run_mock_asr(
    mock_text: str, mock_confidence: float
) -> tuple[str, float, str, dict[str, Any]]:
    """不碰 AWS 的介面與 failure-path 測試；文字必須是 Synthetic。"""
    transcript = mock_text.strip()
    needs_confirmation = confirmation_required(mock_confidence, transcript)
    status = "需要人工確認。" if needs_confirmation else "Mock 信心值達門檻。"
    return (
        transcript,
        mock_confidence,
        status,
        {
            "provider": "mock",
            "language": "synthetic",
            "confidence": mock_confidence,
            "confirmation_threshold": CONFIDENCE_THRESHOLD,
            "needs_confirmation": needs_confirmation,
            "latency_ms": 0.0,
            "model_version": "mock-v1",
        },
    )


def call_core_agent(
    transcript: str,
    confirmed: bool,
    session_id: str,
    core_url: str,
    bearer_token: str,
) -> tuple[str, str, dict[str, Any]]:
    """只呼叫 Core 的正式 Gate；絕不從 GUI 直接信任 actor／tenant 欄位。"""
    if not confirmed:
        raise gr.Error("逐字稿尚未人工確認，禁止送往 Agent／RAG。")
    if not transcript.strip():
        raise gr.Error("確認後逐字稿不可為空。")
    try:
        uuid.UUID(session_id)
    except ValueError as exc:
        raise gr.Error("Session ID 必須是 UUID。") from exc
    if not bearer_token.strip():
        raise gr.Error("請提供測試環境的短效 Bearer Token；Token 不會寫入檔案。")

    correlation_id = str(uuid.uuid4())
    try:
        response = httpx.post(
            f"{core_url.rstrip('/')}/api/v1/voice-sessions/{session_id}/companion-turns",
            json={"input_text": transcript.strip()},
            headers={
                "Authorization": f"Bearer {bearer_token.strip()}",
                "Idempotency-Key": f"speech-{uuid.uuid4()}",
                "X-Correlation-ID": correlation_id,
            },
            timeout=35.0,
        )
        response.raise_for_status()
        data = response.json()["data"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise gr.Error(f"Core／Agent 呼叫失敗：{type(exc).__name__}") from exc

    metadata = {
        "agent_run_id": data.get("agent_run_id"),
        "trace_id": data.get("trace_id"),
        "context_manifest_id": data.get("context_manifest_id"),
        "result_status": data.get("result_status"),
        "safety_decision": data.get("safety_decision"),
        "risk_level": data.get("risk_level"),
        "reason_codes": data.get("reason_codes", []),
        "model_route": data.get("model_route"),
        "correlation_id": correlation_id,
    }
    return str(data["reply_text"]), str(data["reply_language"]), metadata


def synthesize_external_tts(
    text: str,
    language_label: str,
    synthetic_only: bool,
    hakka_dialect: str,
    speed: float,
    taiwanese_model: str,
) -> tuple[str, dict[str, Any]]:
    """第三方 Space 僅供 Synthetic 評估；正式長者文字一律拒絕。"""
    if not synthetic_only:
        raise gr.Error("第三方 TTS 只允許 Synthetic／完成去識別文字。")
    text = text.strip()
    if not text or len(text) > 200:
        raise gr.Error("測試文字必須為 1～200 字。")
    language = LANGUAGES[language_label]
    started = time.perf_counter()
    try:
        if language == "hak-TW":
            segmented, romanization, audio_path = Client(
                "ivanusto/tw-hakka-tts"
            ).predict(
                model_id="yourtts-htia-240704",
                use_default_emb_or_custom="預設語者",
                speaker_wav=None,
                speaker="朱品諭",
                dialect=hakka_dialect,
                speed=speed,
                text=text,
                api_name="/predict",
            )
            provider_detail = {
                "dialect": hakka_dialect,
                "romanization": romanization,
                "segmented_text": segmented,
            }
            provider = "ivanusto/tw-hakka-tts"
        else:
            result = Client("tbdavid2019/Taiwanese-tts").predict(
                text=text, model=taiwanese_model, api_name="/handle_tts"
            )
            audio_path, status, tailo, ipa = result[:4]
            provider_detail = {"status": status, "tailo": tailo, "ipa": ipa}
            provider = "tbdavid2019/Taiwanese-tts"
    except Exception as exc:
        raise gr.Error(f"外部 TTS 呼叫失敗：{type(exc).__name__}") from exc
    metadata = {
        "provider": provider,
        "language": language,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "data_classification": "synthetic_or_deidentified_only",
        **provider_detail,
    }
    return str(audio_path), metadata


def invoke_sagemaker_tts(
    text: str,
    language_label: str,
    endpoint_name: str,
    region: str,
    speed_label: str,
) -> tuple[str, dict[str, Any]]:
    text = text.strip()
    if not text or len(text) > 4000:
        raise gr.Error("TTS 文字必須為 1～4000 字。")
    started = time.perf_counter()
    try:
        response = boto3.client(
            "sagemaker-runtime", region_name=region
        ).invoke_endpoint(
            EndpointName=endpoint_name.strip(),
            ContentType="application/json",
            Body=json.dumps(
                {
                    "text": text,
                    "language": LANGUAGES[language_label],
                    "speakingSpeed": speed_label,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )
        audio_bytes = response["Body"].read()
        if not audio_bytes.startswith(b"RIFF"):
            raise ValueError("Endpoint 未回傳 WAV")
    except Exception as exc:
        raise gr.Error(f"SageMaker TTS 呼叫失敗：{type(exc).__name__}") from exc
    output = Path(tempfile.gettempdir()) / f"kinsun-tts-{uuid.uuid4().hex}.wav"
    output.write_bytes(audio_bytes)
    return str(output), {
        "provider": "aws-sagemaker",
        "endpoint": endpoint_name.strip(),
        "language": LANGUAGES[language_label],
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "content_type": response.get("ContentType"),
    }


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="Kinsun Speech 整合工作台") as demo:
        gr.Markdown("# Kinsun Speech 整合工作台（成員 D）")
        gr.Markdown(
            "僅限 Synthetic／去識別資料。正式串接固定走 "
            "**ASR → 人工確認 → Core Authorization/Consent → Agent/RAG → TTS**。"
        )
        gr.Markdown(
            "**ASR 語言範圍：**這個 SageMaker endpoint 專門處理台語 `nan-TW` 與"
            "客語 `hak-TW`；兩者使用同一個 Taiwan-Tongues 模型。華語／英語依目標"
            "架構走 AWS Transcribe，不會送到這個 endpoint。下拉選單預設台語不代表"
            "模型只有台語。"
        )
        with gr.Tab("1. ASR 與低信心確認"):
            with gr.Row():
                audio = gr.Audio(
                    label="錄音或上傳音訊",
                    sources=["microphone", "upload"],
                    type="filepath",
                )
                with gr.Column():
                    asr_language = gr.Dropdown(
                        list(LANGUAGES), value="台語（nan-TW）", label="語言"
                    )
                    asr_endpoint = gr.Textbox(
                        value=DEFAULT_ASR_ENDPOINT, label="SageMaker ASR Endpoint"
                    )
                    asr_region = gr.Textbox(value=DEFAULT_REGION, label="AWS Region")
                    asr_run = gr.Button("執行 SageMaker ASR", variant="primary")
            with gr.Accordion("Mock 模式（不呼叫 AWS）", open=False):
                mock_text = gr.Textbox(
                    value="這是一段 Synthetic 測試逐字稿。", label="Mock 逐字稿"
                )
                mock_conf = gr.Slider(
                    0, 1, value=0.5, step=0.01, label="Mock confidence"
                )
                mock_run = gr.Button("執行 Mock ASR")
            transcript = gr.Textbox(label="可修正逐字稿", lines=4)
            confidence = gr.Number(label="ASR confidence", precision=4)
            asr_status = gr.Textbox(label="確認狀態", interactive=False)
            confirmed = gr.Checkbox(label="我已人工確認逐字稿正確")
            asr_metadata = gr.JSON(label="ASR Metadata（不含音訊）")
            asr_run.click(
                invoke_sagemaker_asr,
                [audio, asr_language, asr_endpoint, asr_region],
                [transcript, confidence, asr_status, asr_metadata],
            )
            mock_run.click(
                run_mock_asr,
                [mock_text, mock_conf],
                [transcript, confidence, asr_status, asr_metadata],
            )

        with gr.Tab("2. Core → Agent／RAG"):
            gr.Markdown(
                "必須先在上一頁確認逐字稿；正式權限與 Consent 由 Core 重新檢查。"
            )
            core_url = gr.Textbox(value=DEFAULT_CORE_URL, label="Core API URL")
            session_id = gr.Textbox(label="已授權 Voice Session UUID")
            token = gr.Textbox(label="短效 Bearer Token（不保存）", type="password")
            agent_run = gr.Button("送往 Core／Agent／RAG", variant="primary")
            agent_reply = gr.Textbox(label="安全回覆", lines=4)
            reply_language = gr.Textbox(label="回覆語言")
            agent_metadata = gr.JSON(label="Agent Safety／Trace Metadata")
            agent_run.click(
                call_core_agent,
                [transcript, confirmed, session_id, core_url, token],
                [agent_reply, reply_language, agent_metadata],
            )

        with gr.Tab("3. TTS 與播放"):
            tts_text = gr.Textbox(label="要合成的文字", lines=4)
            copy_reply = gr.Button("使用 Agent 回覆")
            copy_reply.click(lambda value: value, agent_reply, tts_text)
            with gr.Row():
                tts_language = gr.Dropdown(
                    list(LANGUAGES), value="客語（hak-TW）", label="語言"
                )
                hakka_dialect = gr.Dropdown(
                    HAKKA_DIALECTS, value="sixian", label="客語腔調"
                )
                speed = gr.Slider(
                    0.5, 1.5, value=1.0, step=0.1, label="外部客語語速（越大越慢）"
                )
                nan_model = gr.Dropdown(
                    ["model5", "model6", "model7"], value="model6", label="外部台語模型"
                )
            synthetic_only = gr.Checkbox(
                label="確認文字為 Synthetic／完成去識別（第三方 API 必填）"
            )
            external_run = gr.Button("呼叫外部候選 TTS")
            with gr.Accordion("SageMaker TTS 設定", open=False):
                tts_endpoint = gr.Textbox(
                    value=DEFAULT_TTS_ENDPOINT, label="SageMaker TTS Endpoint"
                )
                tts_region = gr.Textbox(value=DEFAULT_REGION, label="AWS Region")
                speed_label = gr.Dropdown(
                    ["slow", "normal", "fast"], value="normal", label="語速"
                )
                sagemaker_tts_run = gr.Button("呼叫 SageMaker TTS", variant="primary")
            tts_audio = gr.Audio(label="合成語音", type="filepath")
            tts_metadata = gr.JSON(label="TTS Metadata")
            external_run.click(
                synthesize_external_tts,
                [
                    tts_text,
                    tts_language,
                    synthetic_only,
                    hakka_dialect,
                    speed,
                    nan_model,
                ],
                [tts_audio, tts_metadata],
            )
            sagemaker_tts_run.click(
                invoke_sagemaker_tts,
                [tts_text, tts_language, tts_endpoint, tts_region, speed_label],
                [tts_audio, tts_metadata],
            )
    return demo


def main() -> None:
    port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    build_demo().launch(
        server_name="127.0.0.1", server_port=port, share=False, show_error=False
    )


if __name__ == "__main__":
    main()
