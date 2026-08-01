class CoreToolClientError(Exception):
    """Sanitized base error for Core Tool transport and protocol failures."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.retryable = retryable
        self.status_code = status_code


class CoreToolTransportError(CoreToolClientError):
    def __init__(
        self,
        message: str = "Core Tool service is unavailable",
        *,
        reason_code: str = "CORE_TOOL_UNAVAILABLE",
    ) -> None:
        super().__init__(
            message,
            reason_code=reason_code,
            retryable=True,
        )


class CoreToolTimeoutError(CoreToolTransportError):
    """Specific retryable transport failure used for timeout terminal mapping."""

    def __init__(self) -> None:
        super().__init__(
            "Core Tool request timed out",
            reason_code="CORE_TOOL_TIMEOUT",
        )


class CoreToolProtocolError(CoreToolClientError):
    def __init__(self, *, status_code: int | None = None) -> None:
        super().__init__(
            "Core Tool response did not match the executable contract",
            reason_code="CORE_TOOL_PROTOCOL_ERROR",
            retryable=False,
            status_code=status_code,
        )


class CoreToolHttpError(CoreToolClientError):
    """A valid Core ErrorEnvelope returned for a non-success HTTP status."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        reason_code: str | None,
        retryable: bool,
    ) -> None:
        super().__init__(
            "Core Tool request was rejected",
            reason_code=reason_code or code,
            retryable=retryable,
            status_code=status_code,
        )
        self.code = code
