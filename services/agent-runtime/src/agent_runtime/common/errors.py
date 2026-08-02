"""Domain-level errors for service orchestration."""


class DomainError(Exception):
    """Base domain error."""


class InvalidRequestError(DomainError):
    """The request is invalid under domain policy or schema."""


class StepLimitError(DomainError):
    """Agent flow exceeded an allowed decision or Tool limit."""


class CoreDependencyError(DomainError):
    """A required Core registration or Tool gate failed closed."""


class ModelDependencyError(DomainError):
    """The model provider could not produce a reply.

    A domain error rather than a bare exception on purpose. The unhandled
    handler logs a full traceback, and a provider exception chain can quote the
    request body, which is the elder speaking. Classifying this keeps the
    transcript out of ordinary logs while still answering 5xx, so a provider
    outage stays visible instead of being dressed up as a conversation.
    """
