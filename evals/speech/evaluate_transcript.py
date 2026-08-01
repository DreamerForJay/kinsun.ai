"""針對 Synthetic／去識別語音證據計算可重現的逐字稿指標。"""

from __future__ import annotations

import argparse
import csv
import html
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
    found = sum(
        normalize_hanji(term) in normalized_hypothesis for term in required_terms
    )
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
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if line.strip():
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on line {line_number}") from error
    return cases


def write_table_reports(
    results: list[dict[str, Any]], json_output: Path
) -> tuple[Path, Path]:
    """輸出 CSV 與可直接開啟的 HTML，讓團隊不用 Notebook 也能看 CER。"""
    csv_path = json_output.with_suffix(".csv")
    html_path = json_output.with_suffix(".html")
    columns = [
        "case_id",
        "language",
        "model_id",
        "model_revision",
        "latency_ms",
        "raw_hanji_cer",
        "normalized_hanji_cer",
        "tailo_cer",
        "keyword_recall",
        "negation_recall",
        "semantic_intent_correct",
        "reference_hanji",
        "asr_raw_output",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(results)

    def display(value: Any, column: str) -> str:
        if value is None:
            return "N/A"
        if column.endswith(("_cer", "_recall")):
            return f"{float(value) * 100:.1f}%"
        return html.escape(str(value))

    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    rows = "".join(
        "<tr>"
        + "".join(f"<td>{display(row.get(column), column)}</td>" for column in columns)
        + "</tr>"
        for row in results
    )
    html_path.write_text(
        "<!doctype html><html lang='zh-Hant'><meta charset='utf-8'>"
        "<title>Kinsun Speech Evaluation</title>"
        "<style>body{font-family:sans-serif;margin:24px}table{border-collapse:collapse}"
        "th,td{border:1px solid #ccc;padding:8px;text-align:left}th{background:#f5f5f5}"
        "</style><h1>Kinsun Speech Evaluation</h1>"
        "<p>僅使用 Synthetic／去識別資料；CER 越低越好，Recall 越高越好。</p>"
        f"<table><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table></html>",
        encoding="utf-8",
    )
    return csv_path, html_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    results = [evaluate_case(case) for case in load_cases(args.input)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"schema_version": "1.0", "results": results}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    csv_path, html_path = write_table_reports(results, args.output)
    print(
        f"evaluated {len(results)} synthetic cases -> "
        f"{args.output}, {csv_path}, {html_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
