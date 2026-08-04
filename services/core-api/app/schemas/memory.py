"""Candidate-before-fact memory schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MemoryType(str, Enum):
    PREFERENCE = "PREFERENCE"
    IMPORTANT_RELATIONSHIP = "IMPORTANT_RELATIONSHIP"
    ROUTINE = "ROUTINE"
    COMMUNICATION_PREFERENCE = "COMMUNICATION_PREFERENCE"
    PERSONAL_HISTORY = "PERSONAL_HISTORY"


class CreateMemoryCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_type: MemoryType
    normalized_content: str = Field(min_length=1, max_length=500)
    source_event_ids: list[UUID] = Field(min_length=1, max_length=16)
    possible_conflict: bool = False
    conflict_with_memory_ids: list[UUID] = Field(default_factory=list, max_length=16)
    confirmation_question: str = Field(min_length=1, max_length=300)
    extractor_version: str = Field(min_length=1, max_length=80)


class ConfirmMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_method: Literal["ELDER_UI", "CAREGIVER_REVIEW", "LEGAL_REPRESENTATIVE"] = Field(
        description=(
            "Only ELDER_UI can activate a candidate. Legacy caregiver and legal "
            "representative values remain parseable during deprecation but fail "
            "closed at the Core authorization gate. VOICE remains unavailable "
            "until candidate-specific affirmative evidence exists."
        )
    )
    expected_candidate_version: int = Field(ge=1)
    consent_version: int = Field(ge=1)


class MemoryDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(min_length=1, max_length=120)
    expected_version: int = Field(ge=1)


class UpdateMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)
    reason_code: str = Field(min_length=1, max_length=120)


class MemoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    elder_id: UUID
    memory_type: MemoryType
    content: str
    status: Literal[
        "CANDIDATE",
        "CONFIRMED",
        "ACTIVE",
        "DEFERRED",
        "REJECTED",
        "INACTIVE",
        "DELETED",
    ]
    source_event_ids: list[UUID]
    confirmed_by: UUID | None
    confirmed_at: datetime | None
    version: int
    active_from: datetime | None
    inactive_at: datetime | None
    consent_version: int
    graph_projection_status: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MemoryResponse]
    next_cursor: str | None
    has_more: bool


class MemoryDeletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    status: Literal["DELETED"]
