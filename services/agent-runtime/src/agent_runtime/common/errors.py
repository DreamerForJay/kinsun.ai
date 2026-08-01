"""Domain-level errors for service orchestration."""


class DomainError(Exception):
    """Base domain error."""


class InvalidRequestError(DomainError):
    """The request is invalid under domain policy or schema."""


class StepLimitError(DomainError):
    """Agent flow exceeded an allowed decision or Tool limit."""


class CoreDependencyError(DomainError):
    """A required Core registration or Tool gate failed closed."""
