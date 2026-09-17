"""Exception classes for targetprocess-py."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, ClassVar


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


class _Absent:
    """The observed side of a requested field the re-read did not carry."""

    def __repr__(self) -> str:
        """Render as ``<absent>``, the form a mismatch message uses."""
        return "<absent>"


class VerificationError(TargetProcessError):
    """An independent re-read after a write did not show the requested fields.

    Raised by ``update(..., verify=True)`` and ``update_many(..., verify=True)``
    when the entity read back after the write does not carry what the write
    asked for. The write itself was sent and answered with a success status;
    this error is the evidence that the status was not proof the change landed.

    Attributes:
        entity_type: The entity type written (e.g. ``"UserStory"``).
        entity_id: The entity written, for a single-entity update; ``None``
            for a bulk update.
        mismatches: Entity Id -> field -> ``(requested, observed)`` for every
            field that did not verify. A field the re-read did not carry at
            all is observed as :attr:`ABSENT`; a custom field is keyed
            ``CustomFields[<name>]``.
        verified_ids: The entities of a bulk update whose re-read matched;
            empty for a single-entity update.
    """

    ABSENT: ClassVar[object] = _Absent()

    def __init__(
        self,
        message: str,
        *,
        entity_type: str,
        entity_id: int | None = None,
        mismatches: Mapping[int, Mapping[str, tuple[Any, Any]]],
        verified_ids: Sequence[int] = (),
    ) -> None:
        """Initialize verification error.

        Args:
            message: Human-readable description naming each mismatch.
            entity_type: The entity type written.
            entity_id: The entity written, for a single-entity update.
            mismatches: Entity Id -> field -> ``(requested, observed)``.
            verified_ids: The entities of a bulk update that did verify.
        """
        super().__init__(message)
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.mismatches = {entity: dict(fields) for entity, fields in mismatches.items()}
        self.verified_ids = list(verified_ids)
