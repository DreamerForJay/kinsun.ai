"""以單一命令執行 Taiwan-Tongues ASR，並輸出可重現的 JSON 證據。"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SPEECH_CORE = REPOSITORY_ROOT / "services" / "speech-gateway" / "sagemaker" / "core"
if str(SPEECH_CORE) not in sys.path:
    sys.path.insert(0, str(SPEECH_CORE))

from evaluate_transcript import evaluate_case
from speech_adapters import TransformersASRAdapter
from speech_contracts import SessionContext

MODEL_ID = "adi-gov-tw/Taiwan-Tongues-ASR-CE-pretrained-v2.0"
LANGUAGE_CODES = {"nan-TW": "nan", "hak-TW": "hak"}


def canonical_wav(source: Path, destination: Path) -> dict[str, object]:
    """解碼常見音訊並統一成 16 kHz 單聲道 WAV，讓每次模型輸入條件一致。"""
    # 大型音訊／模型依賴只在真正執行推論時匯入，讓 `--help` 與參數驗證不要求先裝模型。
    import librosa
    import soundfile as sf

    if not source.is_file():
        raise ValueError(f"找不到音訊檔：{source}")
    if source.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("音訊不可超過 25 MB，請先裁切為單句。")
    waveform, _sample_rate = librosa.load(source, sr=16000, mono=True)
    if waveform.size == 0:
        raise ValueError("音訊內容為空。")
    duration_seconds = len(waveform) / 16000
    if duration_seconds > 120:
        raise ValueError("音訊不可超過 120 秒，請先裁切為單句。")
    sf.write(destination, waveform, 16000, subtype="PCM_16")
    return {
        "source_format": source.suffix.lower().lstrip(".") or "unknown",
        "duration_seconds": round(duration_seconds, 3),
        "canonical_format": "wav-pcm-s16le",
        "sample_rate": 16000,
        "channels": 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="執行 Synthetic／去識別台語或客語本機 ASR")
    parser.add_argument("--audio", required=True, type=Path, help="輸入音訊路徑")
    parser.add_argument("--language", required=True, choices=sorted(LANGUAGE_CODES))
    parser.add_argument("--output", required=True, type=Path, help="結果 JSON 路徑")
    parser.add_argument("--reference", help="選填的正確逐字稿；提供後會同時計算 CER")
    parser.add_argument("--keywords", default="", help="選填，逗號分隔的必要關鍵詞")
    parser.add_argument("--negations", default="", help="選填，逗號分隔的必要否定詞")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="確認輸入不含真實人物資料；未提供此旗標會 fail closed",
    )
    args = parser.parse_args()
    if not args.synthetic:
        parser.error("必須提供 --synthetic，且音訊只能是 Synthetic／已核准去識別資料。")

    language = LANGUAGE_CODES[args.language]
    with tempfile.TemporaryDirectory(prefix="kinsun-local-asr-") as directory:
        wav_path = Path(directory) / "canonical.wav"
        audio_metadata = canonical_wav(args.audio, wav_path)
        adapter = TransformersASRAdapter(
            model_id=MODEL_ID,
            device=-1,
            language_code="chinese",
            chunk_length_s=30,
        )
        context = SessionContext(
            session_id="synthetic-local-evaluation",
            elder_id="synthetic-not-a-real-person",
            preferred_language=language,
            consent_to_process_audio=True,
        )
        result = adapter.transcribe(wav_path, language, context)

    payload: dict[str, object] = {
        "schema_version": "1.0",
        "data_origin": "synthetic-or-approved-deidentified",
        "audio": audio_metadata,
        "asr": {
            "transcript": result.transcript,
            "normalized_transcript": result.normalized_transcript,
            "provider": result.provider,
            "model_id": result.model_id,
            "model_version": result.model_version,
            "latency_ms": result.latency_ms,
            "realtime_factor": result.realtime_factor,
            "needs_confirmation": result.needs_confirmation,
        },
    }
    if args.reference is not None:
        split_terms = lambda value: [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
        payload["evaluation"] = evaluate_case(
            {
                "case_id": args.audio.stem,
                "language": args.language,
                "reference_hanji": args.reference,
                "reference_tailo": None,
                "asr_raw_output": result.transcript,
                "asr_tailo_output": None,
                "required_keywords": split_terms(args.keywords),
                "required_negations": split_terms(args.negations),
                "semantic_intent_correct": None,
                "model": {"model_id": result.model_id, "revision": result.model_version},
                "latency_ms": result.latency_ms,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ASR result written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
