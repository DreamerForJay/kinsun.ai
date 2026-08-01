"""產生 Mock ASR 介面專用、完全不含真人聲音的 Synthetic WAV。"""
from __future__ import annotations

import argparse
import math
import struct
import wave
from pathlib import Path


def generate_tone(path: Path, duration_seconds: float = 1.5) -> None:
    """產生低音量雙提示音，用來驗證 WAV 上傳、播放與檔案處理流程。

    這段音訊不是語音，也不代表任何人的聲紋。Mock adapter 不會分析聲音內容，而是讀取
    同檔名的 `.txt` 逐字稿，因此這個 fixture 不能用來衡量真實 ASR 準確率。
    """
    sample_rate = 16000
    amplitude = 0.18
    frame_count = round(sample_rate * duration_seconds)
    path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for frame_index in range(frame_count):
            elapsed = frame_index / sample_rate
            # 前半段使用 440 Hz、後半段使用 660 Hz，中間保留短暫靜音，方便肉耳確認檔案完整。
            if 0.65 <= elapsed < 0.85:
                sample = 0.0
            else:
                frequency = 440.0 if elapsed < 0.75 else 660.0
                sample = amplitude * math.sin(2.0 * math.pi * frequency * elapsed)
            wav_file.writeframesraw(struct.pack("<h", round(sample * 32767)))


def main() -> int:
    parser = argparse.ArgumentParser(description="產生不含真人語音的 Mock 測試 WAV")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/speech/fixtures/synthetic_mock_tone.wav"),
        help="輸出 WAV 路徑",
    )
    args = parser.parse_args()
    generate_tone(args.output)
    print(f"generated synthetic non-speech WAV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
