#!/usr/bin/env python3
"""以 Synthetic 文字評估公開 Gradio TTS Space。

重要：這支程式會把文字送到第三方服務。為避免把長者資料、逐字稿或其他
Restricted Data 傳出去，必須明確加上 ``--synthetic-only`` 才會執行。
它只供模型候選評估，不是 production Speech Gateway adapter。
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from gradio_client import Client

SYNTHETIC_TEXT = {
    "hak": "食飯愛正經食，正毋會食到半出半入",
    "nan": "我欲講台語，請轉做語音。",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="評估公開 Gradio TTS API")
    parser.add_argument("--provider", choices=("hak", "nan"), required=True)
    parser.add_argument("--text", help="僅可輸入 Synthetic／完成去識別的測試文字")
    parser.add_argument("--output-dir", type=Path, default=Path("evals/reports/tts"))
    parser.add_argument(
        "--synthetic-only",
        action="store_true",
        help="確認輸入不含個資、健康資料、真實逐字稿或其他受限制資料",
    )
    parser.add_argument(
        "--hakka-dialect",
        default="sixian",
        choices=("sixian", "hailu", "dapu", "raoping", "zhaoan", "nansixian"),
    )
    parser.add_argument("--hakka-speaker", default="朱品諭")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument(
        "--taiwanese-model", default="model6", choices=("model5", "model6", "model7")
    )
    return parser.parse_args()


def _copy_audio(source: str, destination: Path) -> None:
    """Gradio Client 會先下載 Space 回傳的暫存檔，再複製到報告目錄。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> int:
    args = _parse_args()
    if not args.synthetic_only:
        raise SystemExit(
            "拒絕傳送：請確認資料為 Synthetic／去識別後加上 --synthetic-only"
        )

    text = (args.text or SYNTHETIC_TEXT[args.provider]).strip()
    if not text or len(text) > 200:
        raise SystemExit("測試文字必須為 1～200 字")

    started = time.perf_counter()
    if args.provider == "hak":
        client = Client("ivanusto/tw-hakka-tts")
        segmented, romanization, audio_path = client.predict(
            model_id="yourtts-htia-240704",
            use_default_emb_or_custom="預設語者",
            speaker_wav=None,
            speaker=args.hakka_speaker,
            dialect=args.hakka_dialect,
            speed=args.speed,
            text=text,
            api_name="/predict",
        )
        metadata = {
            "provider": "ivanusto/tw-hakka-tts",
            "model": "yourtts-htia-240704",
            "language": "hak-TW",
            "dialect": args.hakka_dialect,
            "speaker": args.hakka_speaker,
            "segmented_text": segmented,
            "romanization": romanization,
        }
    else:
        client = Client("tbdavid2019/Taiwanese-tts")
        result = client.predict(
            text=text, model=args.taiwanese_model, api_name="/handle_tts"
        )
        audio_path, status, tailo, ipa = result[:4]
        metadata = {
            "provider": "tbdavid2019/Taiwanese-tts",
            "upstream": "https://learn-language.tokyo/taigiTTS/taigi-text-to-speech",
            "model": args.taiwanese_model,
            "language": "nan-TW",
            "status": status,
            "tailo": tailo,
            "ipa": ipa,
        }

    metadata["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    metadata["input_classification"] = "synthetic_or_deidentified_only"
    # 報告刻意不寫入原始文字；避免日後有人誤用真實內容時留下副本。
    output_dir = args.output_dir / args.provider
    _copy_audio(str(audio_path), output_dir / "output.wav")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(f"音訊：{output_dir / 'output.wav'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
