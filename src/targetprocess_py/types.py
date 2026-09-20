"""Type definitions for targetprocess-py."""

from dataclasses import dataclass
from enum import StrEnum

from targetprocess_py.models import Time


class ClientMode(StrEnum):
    """Client operation mode.

    READONLY: Blocks all write operations (create, update, delete)
    READWRITE: Allows all operations
    """

    READONLY = "readonly"
    READWRITE = "readwrite"


class UpsertAction(StrEnum):
    """Outcome of an upsert.

    CREATED / UPDATED / UNCHANGED: what the call actually did.
    WOULD_CREATE / WOULD_UPDATE: what a ``dry_run=True`` call would have done.
    """

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    WOULD_CREATE = "would_create"
    WOULD_UPDATE = "would_update"


@dataclass(frozen=True)
class UpsertResult:
    """Result of an upsert.

    Attributes:
        action: What the call did, or would have done under ``dry_run``.
        time: The created, updated, or matched entry. ``None`` only for
            ``WOULD_CREATE``, where no entry exists yet. Hydration differs by
            action: for ``UNCHANGED`` / ``WOULD_UPDATE`` this is the entry as
            returned by ``find_for_day``'s default include set, so fields
            outside it - ``assignable``, ``user``, ``project``, ``role`` -
            are ``None``; for ``CREATED`` / ``UPDATED`` it is parsed from
            TP's write response and fully hydrated. Code that reads e.g.
            ``result.time.assignable.id`` works on one path and raises
            ``AttributeError`` on the other.
        changed_fields: Model field names written, or that would be written.
            Drawn from the mutable set ``spent`` / ``description`` /
            ``remain`` / ``is_estimation``; empty for ``UNCHANGED``.
    """

    action: UpsertAction
    time: Time | None
    changed_fields: frozenset[str]


@dataclass(frozen=True)
class LevelState:
    """One entity-state level of a work item.

    Attributes:
        state_id: The EntityState's Id.
        state_name: The EntityState's name, as the read carried it.
        workflow_id: The Id of the workflow the state belongs to.
    """

    state_id: int
    state_name: str | None
    workflow_id: int


@dataclass(frozen=True)
class StateLevels:
    """A work item's two entity-state levels, read together.

    Attributes:
        project: The project-workflow state, carried on the item itself.
        team: The team-workflow state, carried on the item's team assignment -
            the lane a team board shows. ``None`` when the item has no team
            assignment.
        team_assignment_id: The team assignment carrying ``team``; ``None``
            when there is none.
        collapsed: Whether both levels belong to one workflow, so that the team
            level is not a state of its own and one write moves both. ``False``
            when there is no team level.
    """

    project: LevelState
    team: LevelState | None
    team_assignment_id: int | None
    collapsed: bool
