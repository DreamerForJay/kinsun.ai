"""Strict schema tests for candidate, review, consent, report, and Tool gates."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.assignment import CreateAssignmentRequest
from app.schemas.care_event import CreateCareEventCandidateRequest, ReviewCareEventRequest
from app.schemas.consent import CreateConsentRequest, RevokeConsentRequest
from app.schemas.conversation import ConsumeVoiceTicketRequest, CreateVoiceTicketRequest
from app.schemas.memory import CreateMemoryCandidateRequest
from app.schemas.report import CreateFamilyReportDraftRequest, PublishFamilyReportRequest
from app.schemas.summary import CreateSummaryDraftRequest, ReviewSummaryRequest
from app.schemas.tool import ToolRequest
from app.services.tool_service import ToolExecutionService


def test_voice_ticket_request_rejects_text_only_and_extra_scope() -> None:
    with pytest.raises(ValidationError):
        CreateVoiceTicketRequest(
            language_preference="ZH_TW",
            input_mode="text",
        )
    with pytest.raises(ValidationError):
        CreateVoiceTicketRequest(
            language_preference="ZH_TW",
            input_mode="voice",
            tenant_id=uuid4(),
        )


def test_voice_ticket_consume_request_is_strict_and_bounded() -> None:
    with pytest.raises(ValidationError):
        ConsumeVoiceTicketRequest(session_id=uuid4(), voice_ticket="too-short")
    with pytest.raises(ValidationError):
        ConsumeVoiceTicketRequest(
            session_id=uuid4(),
            voice_ticket="x" * 43,
            actor_id=uuid4(),
        )


def test_consent_requires_explicit_confirmation() -> None:
    with pytest.raises(ValidationError):
        CreateConsentRequest(
            purposes=["BASIC_VOICE"],
            actor_confirmation=False,
            policy_version="consent-v1",
        )


def test_consent_rejects_duplicate_purposes() -> None:
    with pytest.raises(ValidationError):
        CreateConsentRequest(
            purposes=["BASIC_VOICE", "BASIC_VOICE"],
            actor_confirmation=True,
            policy_version="consent-v1",
        )


def test_revocation_rejects_unknown_deletion_scope() -> None:
    with pytest.raises(ValidationError):
        RevokeConsentRequest(
            reason_code="ELDER_REQUEST",
            request_deletion=True,
            revoke_scope=["UNKNOWN_STORE"],
        )


@pytest.mark.parametrize(
    "restricted_key",
    ["transcript", "transcript_text", "audio", "audio_uri", "prompt", "secret"],
)
def test_event_candidate_rejects_restricted_payload_fields(restricted_key: str) -> None:
    with pytest.raises(ValidationError):
        CreateCareEventCandidateRequest(
            source_type="MANUAL",
            event_type="MEAL",
            structured_payload={restricted_key: "must-not-enter-event"},
            confidence_band="LOW",
            extractor_version="event-extractor-v1",
        )


def test_event_candidate_rejects_nested_restricted_payload_fields() -> None:
    with pytest.raises(ValidationError):
        CreateCareEventCandidateRequest(
            source_type="MANUAL",
            event_type="ACTIVITY",
            structured_payload={"evidence": {"transcript": "restricted"}},
            confidence_band="HIGH",
            extractor_version="event-extractor-v1",
        )


def test_conversation_event_requires_source_session() -> None:
    with pytest.raises(ValidationError):
        CreateCareEventCandidateRequest(
            source_type="CONVERSATION_SESSION",
            event_type="MEAL",
            structured_payload={"meal_status": "mentioned"},
            confidence_band="MEDIUM",
            extractor_version="event-extractor-v1",
        )


def test_event_correction_requires_corrected_payload() -> None:
    with pytest.raises(ValidationError):
        ReviewCareEventRequest(
            decision="CORRECT",
            reason_code="FACT_CORRECTION",
            expected_version=1,
        )


def test_memory_candidate_requires_a_source_event() -> None:
    with pytest.raises(ValidationError):
        CreateMemoryCandidateRequest(
            memory_type="PREFERENCE",
            normalized_content="喜歡聽歌仔戲",
            source_event_ids=[],
            confirmation_question="您希望我記住您喜歡歌仔戲嗎？",
            extractor_version="memory-extractor-v1",
        )


def test_summary_requires_sources_or_explicit_missing_fields() -> None:
    with pytest.raises(ValidationError):
        CreateSummaryDraftRequest(summary_date=date(2026, 7, 31))


def test_summary_review_has_no_correction_backdoor() -> None:
    with pytest.raises(ValidationError):
        ReviewSummaryRequest(
            decision="VERIFY",
            reason_code="REVIEWED",
            expected_version=1,
            corrected_text="unversioned edit",
        )


def test_report_draft_requires_source_records() -> None:
    with pytest.raises(ValidationError):
        CreateFamilyReportDraftRequest(
            recipient_scope_ids=[uuid4()],
            report_type="DAILY",
            period_start=date(2026, 7, 31),
            period_end=date(2026, 7, 31),
        )


def test_report_publish_requires_positive_safety_review() -> None:
    with pytest.raises(ValidationError):
        PublishFamilyReportRequest(
            expected_version=1,
            safety_review_passed=False,
            reason_code="REVIEWED",
        )


def test_assignment_rejects_reversed_service_window() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        CreateAssignmentRequest(
            care_unit_id=uuid4(),
            elder_id=uuid4(),
            worker_actor_id=uuid4(),
            service_start=now,
            service_end=now - timedelta(minutes=1),
            allowed_data_scopes=["elder:basic:read"],
        )


def test_tool_request_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValidationError):
        ToolRequest(
            tool_call_id=uuid4(),
            agent_run_id=uuid4(),
            tool_name="retrieve_confirmed_memory",
            tool_version="1.0",
            elder_id=uuid4(),
            purpose="LONG_TERM_MEMORY",
            consent_version=1,
            policy_version="policy-v1",
            request_id="request-1",
            parameters={},
            full_prompt="must-not-be-accepted",
        )


def test_tool_request_rejects_nested_restricted_parameters() -> None:
    with pytest.raises(ValidationError):
        ToolRequest(
            tool_call_id=uuid4(),
            agent_run_id=uuid4(),
            tool_name="create_event_candidate",
            tool_version="1.0",
            elder_id=uuid4(),
            purpose="CARE_EVENT_EXTRACTION",
            consent_version=1,
            policy_version="policy-v1",
            request_id="request-1",
            idempotency_key="idempotency-1",
            parameters={"structured_payload": {"full_prompt": "restricted"}},
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 5), (1, 1), ("7", 7), (99, 10)],
)
def test_tool_limit_is_bounded(value: object, expected: int) -> None:
    assert ToolExecutionService._bounded_limit(value, default=5, maximum=10) == expected


@pytest.mark.parametrize("value", [0, -1, True, "not-an-integer"])
def test_tool_limit_rejects_invalid_values(value: object) -> None:
    with pytest.raises(Exception) as exc_info:
        ToolExecutionService._bounded_limit(value, default=5, maximum=10)
    assert type(exc_info.value).__name__ == "ValidationError"


def test_event_candidate_accepts_opaque_evidence_reference() -> None:
    evidence_ref = f"evidence:{uuid4()}"

    request = CreateCareEventCandidateRequest(
        source_type="MANUAL",
        event_type="MEAL",
        structured_payload={"meal_status": "mentioned"},
        evidence_refs=[evidence_ref],
        confidence_band="MEDIUM",
        extractor_version="event-extractor-v1",
    )

    assert request.evidence_refs == [evidence_ref]


def test_event_candidate_rejects_transcript_as_evidence_reference() -> None:
    with pytest.raises(ValidationError):
        CreateCareEventCandidateRequest(
            source_type="MANUAL",
            event_type="MEAL",
            structured_payload={"meal_status": "mentioned"},
            evidence_refs=["this raw transcript must not become an evidence reference"],
            confidence_band="MEDIUM",
            extractor_version="event-extractor-v1",
        )


def test_memory_confirmation_rejects_unverifiable_voice_method() -> None:
    from app.schemas.memory import ConfirmMemoryRequest

    with pytest.raises(ValidationError):
        ConfirmMemoryRequest(
            confirmation_method="VOICE",
            expected_candidate_version=1,
            consent_version=1,
        )
