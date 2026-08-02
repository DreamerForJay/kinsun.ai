"""Deterministic state-machine coverage for the Gate 1 domain slice."""

from __future__ import annotations

import pytest

from app.core.exceptions import ConflictError
from app.domain.state_machine import (
    require_assignment_transition,
    require_deletion_item_transition,
    require_deletion_request_transition,
    require_memory_transition,
    require_report_transition,
    require_session_transition,
    require_summary_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("CREATED", "RECORDING"),
        ("RECORDING", "PROCESSING"),
        ("RECORDING", "AWAITING_CONFIRMATION"),
        ("AWAITING_CONFIRMATION", "PROCESSING"),
        ("PROCESSING", "RESPONDING"),
        ("RESPONDING", "COMPLETED"),
        ("CREATED", "CANCELLED"),
    ],
)
def test_voice_session_allows_defined_transitions(current: str, target: str) -> None:
    require_session_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("CREATED", "COMPLETED"),
        ("COMPLETED", "RECORDING"),
        ("CANCELLED", "PROCESSING"),
        ("AWAITING_CONFIRMATION", "RESPONDING"),
    ],
)
def test_voice_session_rejects_skipped_or_terminal_transitions(
    current: str,
    target: str,
) -> None:
    with pytest.raises(ConflictError):
        require_session_transition(current, target)


def test_memory_candidate_must_be_confirmed_before_active() -> None:
    with pytest.raises(ConflictError):
        require_memory_transition("CANDIDATE", "ACTIVE")
    require_memory_transition("CANDIDATE", "CONFIRMED")
    require_memory_transition("CONFIRMED", "ACTIVE")


def test_deleted_memory_cannot_be_resurrected() -> None:
    with pytest.raises(ConflictError):
        require_memory_transition("DELETED", "ACTIVE")


def test_assignment_requires_confirmation_before_service_start() -> None:
    with pytest.raises(ConflictError):
        require_assignment_transition("DRAFT", "IN_PROGRESS")
    require_assignment_transition("DRAFT", "CONFIRMED")
    require_assignment_transition("CONFIRMED", "IN_PROGRESS")


def test_published_report_can_only_leave_publication_safely() -> None:
    require_report_transition("PUBLISHED", "WITHDRAWN")
    require_report_transition("PUBLISHED", "STALE")
    with pytest.raises(ConflictError):
        require_report_transition("PUBLISHED", "DRAFT")


def test_summary_review_and_rebuild_transitions() -> None:
    require_summary_transition("NEEDS_REVIEW", "READY")
    require_summary_transition("READY", "STALE")
    require_summary_transition("STALE", "NEEDS_REVIEW")
    with pytest.raises(ConflictError):
        require_summary_transition("WITHDRAWN", "READY")


def test_deletion_request_requires_partial_failure_before_retry() -> None:
    require_deletion_request_transition("REQUESTED", "IN_PROGRESS")
    require_deletion_request_transition("IN_PROGRESS", "PARTIAL_FAILED")
    require_deletion_request_transition("PARTIAL_FAILED", "IN_PROGRESS")
    require_deletion_request_transition("IN_PROGRESS", "COMPLETED")


def test_completed_deletion_request_cannot_be_resurrected() -> None:
    with pytest.raises(ConflictError):
        require_deletion_request_transition("COMPLETED", "IN_PROGRESS")


def test_deletion_item_retry_requires_a_failed_attempt() -> None:
    require_deletion_item_transition("PENDING", "PROCESSING")
    require_deletion_item_transition("PROCESSING", "FAILED")
    require_deletion_item_transition("FAILED", "PROCESSING")
    require_deletion_item_transition("PROCESSING", "COMPLETED")
    with pytest.raises(ConflictError):
        require_deletion_item_transition("COMPLETED", "PROCESSING")
