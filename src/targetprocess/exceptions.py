"""Exception classes for targetprocess-py."""

from datetime import date
from typing import Any


class TargetProcessError(Exception):
    """Base exception for all targetprocess-py errors."""


class APIError(TargetProcessError):
    """Error from the TargetProcess API.

    Attributes:
        status_code: HTTP status code from the response
        details: Additional error details (endpoint, method, params, etc.)
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code
            details: Additional error context
        """
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(TargetProcessError):
    """Authentication failed (401)."""


class ForbiddenError(TargetProcessError):
    """Permission denied (403)."""


class NotFoundError(TargetProcessError):
    """Resource not found (404)."""


class RequestValidationError(TargetProcessError):
    """Request validation failed (400)."""


class RateLimitError(TargetProcessError):
    """Rate limit exceeded (429)."""


class NetworkError(TargetProcessError):
    """Transport-level failure (connection error, timeout, DNS failure, ...).

    Wraps an underlying ``httpx.HTTPError`` raised while sending a request -
    i.e. no HTTP response was received at all.
    """


class ParseError(TargetProcessError):
    """Response body failed model validation.

    Wraps an underlying ``pydantic.ValidationError`` raised while parsing a
    successful HTTP response into an entity model.
    """


class ReadOnlyViolation(TargetProcessError):  # noqa: N818 - published name; renaming breaks callers
    """Attempted write refused before any request was sent.

    Raised when the client is in READONLY mode, or - regardless of mode -
    when the target collection is one TP itself declares read-only (see
    ``BaseResource.server_read_only``).
    """

    def __init__(
        self,
        operation: str | None = None,
        resource: str | None = None,
        *,
        reason: str = "client is in readonly mode",
    ) -> None:
        """Initialize readonly violation.

        Args:
            operation: The attempted operation (create, update, delete) - optional
            resource: The resource type being accessed - optional
            reason: Why the write was refused (defaults to the readonly-mode
                message; a server-side read-only collection passes its own)
        """
        if operation and resource:
            message = f"Cannot perform '{operation}' on '{resource}': {reason}"
        else:
            message = f"Cannot perform write operation: {reason}"
        super().__init__(message)
        self.operation = operation
        self.resource = resource


class AmbiguousMatchError(TargetProcessError):
    """A key or lookup that must identify at most one record matched several.

    Raised wherever a caller-supplied key should resolve to zero-or-one
    records but the API returned more than one - picking a candidate
    arbitrarily would make behaviour non-deterministic, so the call refuses
    instead. Two current call sites:

    - :meth:`PrioritiesResource.resolve` - a priority name that is not
      unique within its entity type.
    - :meth:`TimesResource.upsert` - an ``(assignable, user, day)`` key that
      matches several Time entries.

    Attributes:
        assignable_id: Assignable the key targeted, if applicable.
        user_id: User the key targeted, if applicable.
        day: Calendar day the key targeted, if applicable.
        count: Number of matching entries found, if applicable.
    """

    def __init__(
        self,
        message: str,
        *,
        assignable_id: int | None = None,
        user_id: int | None = None,
        day: date | None = None,
        count: int | None = None,
    ) -> None:
        """Initialize ambiguous-match error.

        Args:
            message: Human-readable description of the ambiguous match.
            assignable_id: Assignable the key targeted, if applicable.
            user_id: User the key targeted, if applicable.
            day: Calendar day the key targeted, if applicable.
            count: Number of matching entries found, if applicable.
        """
        super().__init__(message)
        self.assignable_id = assignable_id
        self.user_id = user_id
        self.day = day
        self.count = count
