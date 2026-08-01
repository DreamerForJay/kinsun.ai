"""針對 Synthetic／去識別語音證據計算可重現的逐字稿指標。"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

_HANJI_PUNCTUATION = re.compile(r"[\s，。！？；：、,.!?;:'\"()（）《》〈〉「」『』—-]+")


def normalize_hanji(text: str) -> str:
    """只正規化 Unicode、空白與標點，不把臺語意譯成華語。

    保留詞彙差異是刻意的：例如「猶未」與「還沒」語意接近，但前者是逐字稿
    Reference 的原詞；若在這裡直接互換，CER 就無法揭露模型發生華語改寫。
    """
    return _HANJI_PUNCTUATION.sub("", unicodedata.normalize("NFKC", text)).strip()


def normalize_tailo(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text).casefold()
    return re.sub(r"[\s,.;:!?()]+", "", normalized)


def edit_distance(reference: str, hypothesis: str) -> int:
    """使用動態規劃計算 Levenshtein distance，空間複雜度為 O(len(hypothesis))。"""
    previous = list(range(len(hypothesis) + 1))
    for reference_index, reference_char in enumerate(reference, start=1):
        current = [reference_index]
        for hypothesis_index, hypothesis_char in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[hypothesis_index] + 1,
                    previous[hypothesis_index - 1]
                    + (reference_char != hypothesis_char),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    """以 Reference 字元數為分母計算 CER；空 Reference 採 fail-closed 處理。"""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return edit_distance(reference, hypothesis) / len(reference)


def term_recall(required_terms: list[str], hypothesis: str) -> float | None:
    """計算必要關鍵詞的逐字保存率；沒有指定詞時回傳 None，避免誤顯示 100%。"""
    if not required_terms:
        return None
    normalized_hypothesis = normalize_hanji(hypothesis)
    found = sum(normalize_hanji(term) in normalized_hypothesis for term in required_terms)
    return found / len(required_terms)


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    """計算單一案例；人工語意判定只原樣帶出，絕不由程式推測。"""
    reference = case["reference_hanji"]
    hypothesis = case["asr_raw_output"]
    normalized_reference = normalize_hanji(reference)
    normalized_hypothesis = normalize_hanji(hypothesis)

    tailo_cer = None
    if case.get("reference_tailo") and case.get("asr_tailo_output"):
        tailo_cer = character_error_rate(
            normalize_tailo(case["reference_tailo"]),
            normalize_tailo(case["asr_tailo_output"]),
        )

    return {
        "case_id": case["case_id"],
        "language": case["language"],
        "model_id": case["model"]["model_id"],
        "model_revision": case["model"]["revision"],
        "latency_ms": case["latency_ms"],
        "raw_hanji_cer": character_error_rate(reference, hypothesis),
        "normalized_hanji_cer": character_error_rate(
            normalized_reference, normalized_hypothesis
        ),
        "tailo_cer": tailo_cer,
        "keyword_recall": term_recall(case["required_keywords"], hypothesis),
        "negation_recall": term_recall(case["required_negations"], hypothesis),
        "semantic_intent_correct": case["semantic_intent_correct"],
        "reference_hanji": reference,
        "asr_raw_output": hypothesis,
    }


def load_cases(path: Path) -> list[dict[str, Any]]:
    """逐行載入 JSONL，錯誤訊息包含行號，方便定位手動編輯問題。"""
    cases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on line {line_number}") from error
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    results = [evaluate_case(case) for case in load_cases(args.input)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"schema_version": "1.0", "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"evaluated {len(results)} synthetic cases -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
