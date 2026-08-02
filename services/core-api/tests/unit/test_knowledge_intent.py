"""Intent routing tests.

The cases that matter most are the negative ones: everyday conversation must stay
conversation. An elder saying "我今天跌倒了" needs a response about their wellbeing,
not a citation list, and routing it to retrieval would be a worse failure than
missing a knowledge question.
"""

from __future__ import annotations

import pytest

from app.services.knowledge_intent import (
    COMPANION_PURPOSE,
    GENERAL_INFORMATION_PURPOSE,
    LEGAL_REFERENCE_PURPOSE,
    is_knowledge_purpose,
    resolve_turn_purpose,
)


@pytest.mark.parametrize(
    "utterance",
    [
        "列出長期照顧服務法第三條的內容",
        "長照服務法第 3 條寫什麼",
        "長照法有規定家屬可以請假嗎",
        "施行細則裡面怎麼寫",
        "第十二條之一的條文是什麼",
    ],
)
def test_statute_questions_route_to_legal_profile(utterance: str) -> None:
    assert resolve_turn_purpose(utterance) == LEGAL_REFERENCE_PURPOSE


@pytest.mark.parametrize(
    "utterance",
    [
        "請問要怎麼申請長照服務",
        "長照2.0有哪些補助",
        "居家服務可以申請多少時數",
        "失智症有什麼照顧建議",
        "老人家防跌要注意什麼",
        "吞嚥困難的飲食要怎麼準備",
        "家庭照顧者有沒有喘息服務",
        "壓傷要如何預防呢",
        "鼻胃管照顧的方式是什麼",
        "覺得孤單有什麼陪伴資源嗎",
    ],
)
def test_topic_questions_route_to_general_information(utterance: str) -> None:
    assert resolve_turn_purpose(utterance) == GENERAL_INFORMATION_PURPOSE


@pytest.mark.parametrize(
    "utterance",
    [
        "我今天吃了麵包",
        "早上天氣很好",
        "我昨天睡得不錯",
        "阿明昨天來看我",
        "我今天心情還可以",
    ],
)
def test_everyday_conversation_stays_companionship(utterance: str) -> None:
    assert resolve_turn_purpose(utterance) == COMPANION_PURPOSE


@pytest.mark.parametrize(
    "utterance",
    [
        "我今天跌倒了",
        "我最近吃不下飯",
        "我覺得很孤單",
        "我忘記有沒有吃藥",
    ],
)
def test_topic_words_without_a_question_stay_companionship(utterance: str) -> None:
    """Reporting something is not asking about it.

    These mention 跌倒/飲食/孤單/用藥 but are statements about the elder's own day.
    Answering them with retrieved guidance would talk past the person.
    """

    assert resolve_turn_purpose(utterance) == COMPANION_PURPOSE


def test_statute_reference_wins_over_general_topic() -> None:
    """The utterance mentions 長照服務 as well; the legal profile is the one that
    can locate a specific provision."""

    assert resolve_turn_purpose("長期照顧服務法第三條對長照服務的定義") == LEGAL_REFERENCE_PURPOSE


@pytest.mark.parametrize("utterance", ["", "   ", "\n"])
def test_blank_input_is_companionship(utterance: str) -> None:
    assert resolve_turn_purpose(utterance) == COMPANION_PURPOSE


def test_is_knowledge_purpose_covers_both_retrieval_routes() -> None:
    assert is_knowledge_purpose(GENERAL_INFORMATION_PURPOSE)
    assert is_knowledge_purpose(LEGAL_REFERENCE_PURPOSE)
    assert not is_knowledge_purpose(COMPANION_PURPOSE)
