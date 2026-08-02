"""Deterministic aggregate state transitions.

LLM output and API payloads never decide formal state directly.  These
functions are the single, testable transition authority for the first Core
Domain vertical slice.
"""

from __future__ import annotations

from app.core.exceptions import ConflictError

SESSION_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"RECORDING", "CANCELLED", "FAILED"}),
    "RECORDING": frozenset({"PROCESSING", "AWAITING_CONFIRMATION", "CANCELLED", "FAILED"}),
    "AWAITING_CONFIRMATION": frozenset({"PROCESSING", "CANCELLED", "FAILED"}),
    "PROCESSING": frozenset({"RESPONDING", "CANCELLED", "FAILED"}),
    "RESPONDING": frozenset({"COMPLETED", "CANCELLED", "FAILED"}),
    "COMPLETED": frozenset(),
    "CANCELLED": frozenset(),
    "FAILED": frozenset(),
}

CARE_EVENT_REVIEW_STATES: dict[str, str] = {
    "VERIFY": "VERIFIED",
    "CORRECT": "CORRECTED",
    "REJECT": "REJECTED",
    "EXCLUDE": "EXCLUDED",
}

MEMORY_TRANSITIONS: dict[str, frozenset[str]] = {
    "CANDIDATE": frozenset({"CONFIRMED", "DEFERRED", "REJECTED", "DELETED"}),
    "CONFIRMED": frozenset({"ACTIVE", "INACTIVE", "DELETED"}),
    "ACTIVE": frozenset({"INACTIVE", "DELETED"}),
    "DEFERRED": frozenset({"CONFIRMED", "REJECTED", "DELETED"}),
    "REJECTED": frozenset({"DELETED"}),
    "INACTIVE": frozenset({"ACTIVE", "DELETED"}),
    "DELETED": frozenset(),
}

ASSIGNMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"CONFIRMED", "CANCELLED"}),
    "CONFIRMED": frozenset({"IN_PROGRESS", "CANCELLED", "EXPIRED", "NO_SHOW"}),
    "IN_PROGRESS": frozenset({"COMPLETED", "CANCELLED", "EXPIRED"}),
    "COMPLETED": frozenset(),
    "EXPIRED": frozenset(),
    "CANCELLED": frozenset(),
    "NO_SHOW": frozenset(),
}

REPORT_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"NEEDS_REVIEW", "PUBLISHED", "WITHDRAWN", "STALE"}),
    "NEEDS_REVIEW": frozenset({"DRAFT", "PUBLISHED", "WITHDRAWN", "STALE"}),
    "PUBLISHED": frozenset({"WITHDRAWN", "STALE"}),
    "WITHDRAWN": frozenset(),
    "STALE": frozenset({"DRAFT", "WITHDRAWN"}),
}

SUMMARY_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"NEEDS_REVIEW", "READY", "STALE", "WITHDRAWN"}),
    "NEEDS_REVIEW": frozenset({"READY", "STALE", "WITHDRAWN"}),
    "READY": frozenset({"PUBLISHED", "STALE", "WITHDRAWN"}),
    "PUBLISHED": frozenset({"STALE", "WITHDRAWN"}),
    "STALE": frozenset({"DRAFT", "NEEDS_REVIEW", "WITHDRAWN"}),
    "WITHDRAWN": frozenset(),
}

DELETION_REQUEST_TRANSITIONS: dict[str, frozenset[str]] = {
    "REQUESTED": frozenset({"IN_PROGRESS", "CANCELLED"}),
    "IN_PROGRESS": frozenset({"PARTIAL_FAILED", "COMPLETED"}),
    "PARTIAL_FAILED": frozenset({"IN_PROGRESS"}),
    "COMPLETED": frozenset(),
    "CANCELLED": frozenset(),
}

DELETION_ITEM_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"PROCESSING"}),
    "PROCESSING": frozenset({"COMPLETED", "FAILED", "SKIPPED"}),
    "FAILED": frozenset({"PROCESSING"}),
    "COMPLETED": frozenset(),
    "SKIPPED": frozenset(),
}


def require_transition(
    aggregate: str,
    current: str,
    target: str,
    transitions: dict[str, frozenset[str]],
) -> None:
    """Reject an undefined formal state transition."""
    if target not in transitions.get(current, frozenset()):
        raise ConflictError(f"Invalid {aggregate} state transition from {current} to {target}")


def require_session_transition(current: str, target: str) -> None:
    require_transition("conversation_session", current, target, SESSION_TRANSITIONS)


def require_memory_transition(current: str, target: str) -> None:
    require_transition("memory", current, target, MEMORY_TRANSITIONS)


def require_assignment_transition(current: str, target: str) -> None:
    require_transition("care_assignment", current, target, ASSIGNMENT_TRANSITIONS)


def require_report_transition(current: str, target: str) -> None:
    require_transition("family_report", current, target, REPORT_TRANSITIONS)


def require_summary_transition(current: str, target: str) -> None:
    require_transition("daily_summary", current, target, SUMMARY_TRANSITIONS)


def require_deletion_request_transition(current: str, target: str) -> None:
    require_transition(
        "deletion_request",
        current,
        target,
        DELETION_REQUEST_TRANSITIONS,
    )


def require_deletion_item_transition(current: str, target: str) -> None:
    require_transition(
        "deletion_job_item",
        current,
        target,
        DELETION_ITEM_TRANSITIONS,
    )
