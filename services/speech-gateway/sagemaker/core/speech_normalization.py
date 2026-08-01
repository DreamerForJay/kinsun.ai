"""Text normalization and conservative confirmation rules."""
from __future__ import annotations

import re
import threading
import unicodedata

_traditional_converter = None
_traditional_converter_lock = threading.Lock()

_tailo_converter = None
_tailo_converter_lock = threading.Lock()

_HAN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def to_tailo(text: str) -> str:
    """Convert Taiwanese Hokkien Han characters to Tai-lo romanization
    (taibun, MIT). No-op when the text contains no Han characters, so
    already-romanized input passes through unchanged.

    Exists because facebook/mms-tts-nan's tokenizer vocab covers only
    romanized Hokkien -- Han input tokenizes to 0 ids and crashes
    VitsModel.forward (see docs/model-selection.md). Verified 2026-08-02:
    the vocab contains Tai-lo tone diacritics (combining U+0304/U+030D and
    precomposed vowels) but NOT POJ's superscript nasal marker U+207F, so
    Tai-lo with tones kept is the correct target system, not POJ.

    Hokkien-only: taibun does not handle Hakka, so this must not be applied
    to hak text (VoxHakka does its own Han->IPA G2P via formog2p anyway).
    """
    if not _HAN_RE.search(text):
        return text
    global _tailo_converter
    if _tailo_converter is None:
        with _tailo_converter_lock:
            if _tailo_converter is None:
                from taibun import Converter
                _tailo_converter = Converter(system="Tailo")
    return _tailo_converter.get(text)


def to_traditional_zh(text: str) -> str:
    """Defensively convert any Simplified characters to Taiwan-standard
    Traditional (OpenCC s2twp). Safe no-op on already-Traditional or
    non-Chinese text. Exists so zh ASR output / TTS input stays Traditional
    even if a future model swap reintroduces Simplified output -- confirmed
    2026-07-31 that openai/whisper-large-v3 does this on this project's own
    zh benchmark set (e.g. 我拿十塊就好 -> 我拿十块就好), which is why its
    CER looked worse than shooding-ct2/taiwan-tongues-transformers even
    though the underlying recognition was often comparable.
    """
    global _traditional_converter
    if _traditional_converter is None:
        with _traditional_converter_lock:
            if _traditional_converter is None:
                from opencc import OpenCC
                _traditional_converter = OpenCC("s2twp")
    return _traditional_converter.convert(text)


HIGH_RISK_TERMS = {
    "藥", "用藥", "吃藥", "服藥", "胰島素", "毫克", "劑量",
    "抗生素", "藥丸", "錠", "膠囊", "早上", "晚上", "幾點",
    "medicine", "medication", "insulin", "milligram", "mg", "antibiotic",
    "tablet", "capsule", "dose", "prescribe", "morning", "evening",
}


def normalize_text(text: str, language: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip()
    if language == "nan":
        # Common Voice nan-tw may include parenthesized Tailo/POJ while the
        # model emits Han text. Remove that annotation for like-for-like CER.
        text = re.sub(r"[（(][^）)]*[）)]", "", text)
    text = re.sub(r"\s+", " ", text)
    if language in {"zh", "nan", "hak", "mixed-zh-nan"}:
        text = re.sub(r"[\s，、。！？；：,.!?;:]+", "", text)
    else:
        text = re.sub(r"[^\w'\s-]", "", text.lower())
    return text


def extract_entities(text: str, expected: list[str]) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return [entity for entity in expected if entity.lower() in normalized]


def requires_confirmation(
    transcript: str,
    confidence: float | None,
    expected_entities: list[str],
    engine_disagreement: bool = False,
    threshold: float = 0.72,
) -> bool:
    lowered = transcript.lower()
    contains_high_risk = any(term in lowered for term in HIGH_RISK_TERMS)
    contains_measurement = bool(
        re.search(r"\b\d+(?:\.\d+)?\s*(?:mg|ml|g|units?)\b", lowered)
        or re.search(r"[零一二三四五六七八九十百千\d]+\s*(?:點|次|顆|錠|毫克)", transcript)
    )
    missing_expected = bool(expected_entities) and not extract_entities(
        transcript, expected_entities
    )
    low_confidence = confidence is None or confidence < threshold
    return (
        not transcript.strip()
        or low_confidence
        or engine_disagreement
        or contains_measurement
        or (contains_high_risk and missing_expected)
    )
