"""Decide whether a companion utterance should be answered from the knowledge base.

The Agent Runtime does not infer this: ``rag_integration.RAG_PURPOSES`` maps the
``purpose`` field on the run request to a retrieval profile, so the choice has to
be made here, before the request is sent.

Two deliberate properties:

* Matching is on subject matter, not document titles. An elder asks "我最近常常
  跌倒怎麼辦", not "請查長者防跌妙招手冊", so keying on file names would leave the
  knowledge base unreachable for the people it exists for.
* Default is companionship, not retrieval. Sending everyday chat through
  retrieval produces citations for "我今天吃了麵包", which is noise at best and an
  invitation to over-trust the answer at worst. When nothing indicates an
  information request, the turn stays a conversation.

Both routes are auditable: the returned purpose is recorded on the AgentRun, so a
reviewer can see whether a given answer was grounded in retrieved sources.
"""

from __future__ import annotations

import re
from typing import Final

# Purpose values recognised by services/agent-runtime rag_integration.RAG_PURPOSES.
# Keep these strings in sync with that module; a typo silently disables retrieval
# because an unknown purpose is treated as a non-RAG turn.
COMPANION_PURPOSE: Final = "BASIC_VOICE"
GENERAL_INFORMATION_PURPOSE: Final = "general_information"
LEGAL_REFERENCE_PURPOSE: Final = "legal_reference"

# Statute-shaped questions route to the `legal` retrieval profile
# (config/rag/hybrid-legal.json), which is tuned for exact provision lookup
# rather than paraphrase.
_LEGAL_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # 第三條 / 第 3 條 / 第三十二條之一
    re.compile(r"第\s*[0-9〇一二三四五六七八九十百]+\s*(條|項|款|目)"),
    re.compile(r"長期照顧服務法|長照服務法|長照法"),
    re.compile(r"法條|法規|條文|施行細則|辦法|自治條例"),
    re.compile(r"(法律|法令)(規定|要求|依據)"),
)

# Subject matter covered by the ingested corpus. Grouped by source document so the
# coverage of each is visible, but matching is on how an elder or caregiver would
# actually phrase the topic.
_KNOWLEDGE_KEYWORDS: Final[tuple[str, ...]] = (
    # 申請長照服務
    "申請長照", "長照申請", "長照2.0", "長照 2.0", "長照服務", "照顧服務",
    "居家服務", "日間照顧", "喘息服務", "交通接送", "輔具", "無障礙",
    "補助", "自付額", "給付額度", "失能等級", "照顧計畫", "1966",
    "長期照顧管理中心", "照管中心", "個案管理", "A單位", "A 單位",
    # 家庭照顧者支持
    "家庭照顧者", "照顧者支持", "照顧壓力", "照顧負荷", "支持團體",
    "照顧技巧", "照顧津貼", "照顧者權益",
    # 高負荷照顧者篩檢與轉介
    "高負荷", "初篩", "轉介",
    # 老年期營養
    "營養", "飲食", "菜單", "熱量", "蛋白質", "吞嚥", "咀嚼", "體重",
    "水分", "脫水", "便祕", "便秘",
    # 防跌
    "跌倒", "防跌", "跌傷", "平衡", "肌力", "步態", "扶手", "止滑",
    # 失智症
    "失智", "阿茲海默", "記憶力", "認知", "重複問", "走失", "定向感",
    "日夜顛倒", "妄想", "幻覺",
    # 居家服務督導與健康照護
    "督導", "居家服務員", "照服員", "身體清潔", "翻身", "拍背", "壓傷",
    "褥瘡", "管路", "鼻胃管", "導尿", "服藥", "用藥", "藥物",
    # 孤獨與情緒（量表與研究文件）
    "孤獨", "寂寞", "孤單", "憂鬱", "情緒低落", "社會參與", "陪伴資源",
)

# Interrogative markers. A topic word alone is not enough: "我今天跌倒了" is
# something to record and respond to with care, while "跌倒要怎麼預防" is a
# request for information. Without this distinction an elder reporting an incident
# would be answered with a citation list instead of concern.
_QUESTION_MARKERS: Final[tuple[str, ...]] = (
    "嗎", "呢", "如何", "怎麼", "怎樣", "為什麼", "什麼", "哪裡", "哪些",
    "多少", "可以", "能不能", "要不要", "是不是", "有沒有", "請問",
    "介紹", "說明", "告訴我", "列出", "查", "規定", "條件", "資格",
    "流程", "步驟", "方式", "方法", "建議", "注意", "?", "？",
)


def _has_question_shape(text: str) -> bool:
    return any(marker in text for marker in _QUESTION_MARKERS)


def resolve_turn_purpose(input_text: str) -> str:
    """Return the ``purpose`` to send to the Agent Runtime for this utterance.

    Statute questions take precedence over general topics: "長期照顧服務法第三條"
    mentions 長照服務 too, but the legal profile is the one that can locate a
    specific provision.
    """

    text = input_text.strip()
    if not text:
        return COMPANION_PURPOSE

    if any(pattern.search(text) for pattern in _LEGAL_PATTERNS):
        return LEGAL_REFERENCE_PURPOSE

    if any(keyword in text for keyword in _KNOWLEDGE_KEYWORDS) and _has_question_shape(text):
        return GENERAL_INFORMATION_PURPOSE

    return COMPANION_PURPOSE


def is_knowledge_purpose(purpose: str) -> bool:
    return purpose in {GENERAL_INFORMATION_PURPOSE, LEGAL_REFERENCE_PURPOSE}
