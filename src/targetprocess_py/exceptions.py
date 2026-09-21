"""Exception classes for targetprocess-py."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, ClassVar


class TargetProcessError(Exception):
    """Base exception for all targetprocess-py errors.

    Every library error survives a pickle round trip with its type, message,
    ``args`` and attributes, so it can be shipped across processes.
    """

    def __reduce__(self) -> tuple[Any, ...]:
        """Pickle without calling ``__init__``, whose parameters ``args`` need not match."""
        return (_unpickle_error, (type(self), self.args), self.__dict__)


def _unpickle_error(cls: type[TargetProcessError], args: tuple[Any, ...]) -> TargetProcessError:
    """Recreate an error from its ``args`` alone, for pickle to restore its attributes onto.

    By default an exception unpickles by calling its class with ``args``. That
    fails for a constructor with required keyword-only arguments, and rebuilds
    the wrong message for one that formats its message from its arguments.
    Creating the instance without running ``__init__`` sidesteps both: ``args``,
    and so the message, are set exactly as they were, and pickle then restores
    every attribute from the instance's ``__dict__``.
    """
    return cls.__new__(cls, *args)


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

    def __reduce__(self) -> str:
        """Pickle by reference, so a round trip yields ``VerificationError.ABSENT`` itself."""
        return "VerificationError.ABSENT"


class VerificationError(TargetProcessError):
    """An independent re-read after a write did not show the requested fields.

    Raised by ``update(..., verify=True)``, ``update_many(..., verify=True)``
    and ``set_custom_field`` when the entity read back after the write does
    not carry what the write asked for. The write itself was sent and
    answered with a success status; this error is the evidence that the
    status was not proof the change landed. It survives a pickle round trip
    with its message, ``args`` and attributes, and :attr:`ABSENT` stays
    :attr:`ABSENT` across one.

    Attributes:
        entity_type: The entity type written (e.g. ``"UserStory"``).
        entity_id: The entity written, for a single-entity update; ``None``
            for a bulk update.
        mismatches: Entity Id -> field -> ``(requested, observed)`` for every
            field that did not verify. A field the re-read did not carry at
            all is observed as :attr:`ABSENT`; a custom field is keyed
            ``CustomFields[<name>]``. A ``CustomFields`` entry without a
            string name, which a verified write refuses before sending, is
            keyed by its zero-based position, ``CustomFields[#<position>]``,
            when the comparison meets one.
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


class TeamIterationCascadeError(VerificationError):
    """A cleared ``TeamIteration`` came back still carrying one.

    Raised by ``AssignableResource.clear_team_iteration`` when the verifying
    re-read after the write shows the field holding a value. TargetProcess
    cascades a parent's team iteration onto its children, so an explicit
    ``null`` on a child is discarded - or applied and immediately re-acquired
    from the parent - and answered with a success status either way, with
    nothing on the response to say the field did not clear.

    A :class:`VerificationError`, so a caller already handling "the re-read did
    not show the write" catches this too. The distinct type is for the caller
    that treats the cascade differently, since the remedy is not a retry:
    unscheduling a child under a scheduled parent means clearing the parent's
    iteration as well, or moving the child out from under it. The value the
    field was observed to hold is in :attr:`VerificationError.mismatches`,
    under ``TeamIteration``, as the observed side of the pair.
    """


class SplitTransitionError(TargetProcessError):
    """An entity-state advance that would leave a work item's two levels apart.

    A work item carries a project-workflow state on itself and a team-workflow
    state on its team assignment. Raised by ``advance_state`` before any write
    when the call would move one level without the other - a team level in a
    workflow of its own with no ``team_to`` given - or would ask one shared
    workflow to hold two different targets. It survives a pickle round trip
    with its message, ``args`` and attributes.

    Attributes:
        entity_id: The work item the advance targeted.
        project_workflow_id: The workflow of the item's own state.
        team_workflow_id: The workflow of its team assignment's state.
    """

    def __init__(
        self,
        message: str,
        *,
        entity_id: int,
        project_workflow_id: int,
        team_workflow_id: int,
    ) -> None:
        """Initialize split-transition error.

        Args:
            message: Human-readable description naming both workflows.
            entity_id: The work item the advance targeted.
            project_workflow_id: The workflow of the item's own state.
            team_workflow_id: The workflow of its team assignment's state.
        """
        super().__init__(message)
        self.entity_id = entity_id
        self.project_workflow_id = project_workflow_id
        self.team_workflow_id = team_workflow_id
