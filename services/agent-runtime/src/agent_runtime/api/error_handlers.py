"""Domain error to ErrorEnvelope mapping.

AGENTS.md 8.3: services raise domain errors; the API layer owns the HTTP
translation. Keeping the status mapping in one table (EXCEPTION_MAP) is the
point — an endpoint that builds its own error payload is how two endpoints end
up disagreeing about what a 422 looks like.

Mirrors ``services/core-api/app/api/error_handlers.py``, with one deliberate
difference documented in ADR 0005: RequestValidationError is also converted to
an ErrorEnvelope here. FastAPI's default ``{"detail": [...]}`` body would
otherwise be the one response shape that escapes the envelope rule, and schema
rejection is the most common error this service returns.
"""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agent_runtime.common.errors import (
    CoreDependencyError,
    DomainError,
    InvalidRequestError,
    ModelDependencyError,
    StepLimitError,
)
from agent_runtime.core.envelopes import ErrorBody, ErrorEnvelope, ValidationDetail
from agent_runtime.middleware.correlation import get_correlation_id

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

EXCEPTION_MAP: dict[type[DomainError], int] = {
    InvalidRequestError: 422,
    StepLimitError: 422,
    CoreDependencyError: 503,
    ModelDependencyError: 503,
}

_STATUS_CODE_SLUGS: dict[int, str] = {
    400: "bad_request",
    422: "validation_error",
    500: "internal_error",
    503: "service_unavailable",
}

_REASON_CODE_BY_EXCEPTION: dict[type[DomainError], str] = {
    InvalidRequestError: "INVALID_AGENT_REQUEST",
    StepLimitError: "AGENT_STEP_LIMIT_EXCEEDED",
    CoreDependencyError: "CORE_EXECUTION_UNAVAILABLE",
}


def _build(
    status_code: int,
    message: str,
    details: list[ValidationDetail] | None = None,
    *,
    reason_code: str,
    retryable: bool = False,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=_STATUS_CODE_SLUGS.get(status_code, "internal_error"),
            message=message,
            correlation_id=get_correlation_id(),
            reason_code=reason_code,
            retryable=retryable,
            details=details,
        )
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


async def _domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status_code = EXCEPTION_MAP.get(type(exc), 500)
    logger.warning(
        "domain_error",
        extra={
            "correlation_id": get_correlation_id(),
            "exception_type": type(exc).__name__,
            "status_code": status_code,
            "path": request.url.path,
        },
    )
    return _build(
        status_code,
        str(exc) or "An error occurred.",
        reason_code=_REASON_CODE_BY_EXCEPTION.get(type(exc), "UNEXPECTED_DOMAIN_ERROR"),
        retryable=status_code >= 500,
    )


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Convert schema rejection into the same envelope every other error uses.

    ``reason`` carries pydantic's error type (``extra_forbidden``,
    ``missing``, ...) rather than its message, and never the rejected value:
    the body of an agent run is elder transcript, and AGENTS.md 8.1 forbids
    echoing a rejected value back when that value is Restricted Data.
    """
    details = [
        ValidationDetail(
            field=".".join(str(part) for part in error.get("loc", ())),
            reason=str(error.get("type", "invalid")),
        )
        for error in exc.errors()
    ]
    return _build(
        422,
        "Request failed schema validation.",
        details,
        reason_code="REQUEST_VALIDATION_FAILED",
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        extra={
            "correlation_id": get_correlation_id(),
            "exception_type": type(exc).__name__,
            "path": request.url.path,
            "traceback": traceback.format_exc(),
        },
    )
    return _build(
        500,
        "Internal server error.",
        reason_code="UNEXPECTED_INTERNAL_ERROR",
        retryable=True,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register every handler on the application.

    The base ``DomainError`` handler covers all subclasses; a subclass missing
    from EXCEPTION_MAP becomes a 500, which is the correct fail-loud behaviour
    for an error nobody has classified yet.
    """
    app.add_exception_handler(DomainError, _domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        _validation_error_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, _unhandled_exception_handler)
