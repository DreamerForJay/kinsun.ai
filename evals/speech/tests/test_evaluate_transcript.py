from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "evaluate_transcript.py"
SPEC = importlib.util.spec_from_file_location("evaluate_transcript", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TranscriptEvaluationTests(unittest.TestCase):
    def test_normalization_does_not_translate_paraphrases(self) -> None:
        self.assertEqual(MODULE.normalize_hanji("我猶未講煞，你先莫插話好無？"), "我猶未講煞你先莫插話好無")
        self.assertNotEqual(
            MODULE.normalize_hanji("我猶未講煞"), MODULE.normalize_hanji("我還沒說完")
        )

    def test_semantically_close_mandarin_output_still_fails_verbatim_metrics(self) -> None:
        case = {
            "case_id": "nan-interruption-001",
            "language": "nan-TW",
            "reference_hanji": "我猶未講煞，你先莫插話好無？",
            "reference_tailo": "Guá iáu-buē kóng-suah, lí sing mài tshah-uē hó--bô?",
            "asr_raw_output": "我還沒說完你先不要吵我好不好。",
            "asr_tailo_output": None,
            "required_keywords": ["講煞", "插話"],
            "required_negations": ["未", "莫"],
            "semantic_intent_correct": True,
            "model": {"model_id": "synthetic-model", "revision": "test"},
            "latency_ms": 550,
        }
        result = MODULE.evaluate_case(case)
        self.assertGreater(result["normalized_hanji_cer"], 0.5)
        self.assertEqual(result["keyword_recall"], 0.0)
        self.assertEqual(result["negation_recall"], 0.0)
        self.assertTrue(result["semantic_intent_correct"])
        self.assertIsNone(result["tailo_cer"])

    def test_exact_transcript_has_zero_cer_and_full_recall(self) -> None:
        transcript = "我猶未講煞，你先莫插話好無？"
        case = {
            "case_id": "exact",
            "language": "nan-TW",
            "reference_hanji": transcript,
            "reference_tailo": None,
            "asr_raw_output": transcript,
            "asr_tailo_output": None,
            "required_keywords": ["講煞", "插話"],
            "required_negations": ["未", "莫"],
            "semantic_intent_correct": True,
            "model": {"model_id": "synthetic-model", "revision": "test"},
            "latency_ms": 1,
        }
        result = MODULE.evaluate_case(case)
        self.assertEqual(result["raw_hanji_cer"], 0.0)
        self.assertEqual(result["normalized_hanji_cer"], 0.0)
        self.assertEqual(result["keyword_recall"], 1.0)
        self.assertEqual(result["negation_recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
