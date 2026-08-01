from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

EVAL_ROOT = Path(__file__).resolve().parents[1]
if str(EVAL_ROOT) not in sys.path:
    sys.path.insert(0, str(EVAL_ROOT))

import run_local_asr


class LocalAsrCommandTests(unittest.TestCase):
    def test_missing_synthetic_confirmation_fails_before_model_load(self) -> None:
        # 即使檔案路徑存在，沒有 --synthetic 也必須在載入 PyTorch／模型前直接拒絕。
        arguments = [
            "run_local_asr.py",
            "--audio",
            "not-used.wav",
            "--language",
            "nan-TW",
            "--output",
            "not-written.json",
        ]
        with patch.object(sys, "argv", arguments), self.assertRaises(SystemExit) as context:
            run_local_asr.main()
        self.assertEqual(context.exception.code, 2)

    def test_language_mapping_is_explicit(self) -> None:
        self.assertEqual(run_local_asr.LANGUAGE_CODES, {"nan-TW": "nan", "hak-TW": "hak"})


if __name__ == "__main__":
    unittest.main()
