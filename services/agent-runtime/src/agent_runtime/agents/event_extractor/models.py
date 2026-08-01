from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, JsonValue, field_validator, model_validator

from agent_runtime.contracts.models import ContractBaseModel

EXTRACTOR_VERSION = "event-extractor-v1"
EVIDENCE_REF_PATTERN = (
    r"^evidence:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_RESTRICTED_PAYLOAD_KEYS = frozenset(
    {
        "audio",
        "audio_uri",
        "transcript",
        "transcript_text",
        "prompt",
        "full_prompt",
        "secret",
        "token",
        "asr_confidence",
    }
)


class EventSourceType(str, Enum):
    CONVERSATION_SESSION = "CONVERSATION_SESSION"
    MANUAL = "MANUAL"


class CareEventType(str, Enum):
    MEAL = "MEAL"
    ACTIVITY = "ACTIVITY"
    SLEEP = "SLEEP"
    MEDICATION_STATEMENT = "MEDICATION_STATEMENT"
    EMOTION_EXPRESSION = "EMOTION_EXPRESSION"
    SOCIAL_CONTACT = "SOCIAL_CONTACT"
    EXPECTED_CONTACT_MISSED = "EXPECTED_CONTACT_MISSED"
    ACTIVITY_PARTICIPATION = "ACTIVITY_PARTICIPATION"
    ACTIVITY_CANCELLED = "ACTIVITY_CANCELLED"
    COMPANIONSHIP_NEED = "COMPANIONSHIP_NEED"


class ConfidenceBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ReviewRequirement(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"


class NoCandidateReason(str, Enum):
    NO_SUPPORTED_EVENT = "NO_SUPPORTED_EVENT"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"


EventSourceTypeField = Annotated[EventSourceType, Field(strict=False)]
CareEventTypeField = Annotated[CareEventType, Field(strict=False)]
ConfidenceBandField = Annotated[ConfidenceBand, Field(strict=False)]
ReviewRequirementField = Annotated[ReviewRequirement, Field(strict=False)]
NoCandidateReasonField = Annotated[NoCandidateReason, Field(strict=False)]
EvidenceReference = Annotated[
    str,
    Field(min_length=45, max_length=45, pattern=EVIDENCE_REF_PATTERN),
]


class EventExtractionContext(ContractBaseModel):
    """Opaque source metadata supplied by the caller, never inferred from transcript text."""

    source_id: UUID
    source_version: int = Field(default=1, ge=1)
    event_time: datetime | None = None
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=16)


class CreateCareEventCandidateRequestV1(ContractBaseModel):
    """Pydantic representation of the existing domain candidate contract."""

    source_type: EventSourceTypeField
    source_id: UUID | None = None
    source_version: int = Field(default=1, ge=1)
    event_type: CareEventTypeField
    event_time: datetime | None = None
    structured_payload: dict[str, JsonValue]
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=16)
    confidence_band: ConfidenceBandField
    review_requirement: ReviewRequirementField = ReviewRequirement.REQUIRED
    extractor_version: str = Field(min_length=1, max_length=80)

    @field_validator("structured_payload")
    @classmethod
    def reject_restricted_payload_keys(cls, payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
        def inspect(value: JsonValue) -> None:
            if isinstance(value, dict):
                for key, nested_value in value.items():
                    if key.casefold() in _RESTRICTED_PAYLOAD_KEYS:
                        raise ValueError("structured_payload contains a restricted key")
                    inspect(nested_value)
            elif isinstance(value, list):
                for nested_value in value:
                    inspect(nested_value)

        inspect(payload)
        return payload

    @model_validator(mode="after")
    def require_conversation_source(self) -> Self:
        if self.source_type is EventSourceType.CONVERSATION_SESSION and self.source_id is None:
            raise ValueError("source_id is required for CONVERSATION_SESSION")
        return self


class NoEventCandidate(ContractBaseModel):
    outcome: Literal["NO_CANDIDATE"] = "NO_CANDIDATE"
    reason_codes: list[NoCandidateReasonField] = Field(min_length=1, max_length=8)


type EventExtractorOutput = CreateCareEventCandidateRequestV1 | NoEventCandidate
