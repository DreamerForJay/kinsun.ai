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
    def __init__(self) -> None:
        super().__init__(
            "Core Tool service is unavailable",
            reason_code="CORE_TOOL_UNAVAILABLE",
            retryable=True,
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
