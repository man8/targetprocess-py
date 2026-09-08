"""Base entity classes, mirroring TargetProcess's own type hierarchy.

TP's ``/meta`` declares a real inheritance chain: most domain types derive from
``General``, and the work-item types derive from ``Assignable``, which itself
derives from ``General``. :class:`GeneralEntity` and :class:`AssignableEntity`
model those two bases, so every field TP defines once is declared once here
rather than repeated on each concrete type.

:class:`Entity` and :class:`NamedEntity` sit above them and carry no TP
counterpart - they hold the identity fields every payload shares and the
``Name`` split, so the types TP exposes outside the ``General`` chain (the
lookup and join types) have a base too.

The concrete entity models live in the sibling private modules and are
re-exported by :mod:`targetprocess.models`, which stays the import surface
callers use.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from targetprocess._dates import TPDateTime
from targetprocess._nested import (
    AssignedUsers,
    CustomFieldValue,
    EntityRef,
    EntityTypeRef,
    RefWithImportance,
    UserRef,
)


class Entity(BaseModel):
    """Base class for all TargetProcess entities.

    Provides the fields common to every TP entity. Entity types that carry no
    ``Name`` field (``User``, ``Comment``, ``Assignment``, ``TeamAssignment``,
    ``RoleEffort``, ``Relation``, ``Time``) extend this base directly; types
    with a display name extend :class:`NamedEntity`, and the ``General`` /
    ``Assignable`` families extend the two bases below that. Pydantic aliases
    handle the API's PascalCase format automatically.

    ``CreateDate`` and ``ModifyDate`` are declared here because most types
    carry them, but TP exposes neither on every type - on a type whose
    ``/meta`` omits them (the lookup and join types, largely) they simply stay
    ``None``.

    Undeclared API fields are never silently discarded: ``extra="allow"``
    preserves them in ``model_extra`` under their wire (PascalCase) names,
    reachable via attribute access and included by ``model_dump``. TP payload
    shapes vary by instance and version, so undeclared keys are tolerated
    rather than rejected - but kept, not dropped. Assigning an undeclared
    attribute (a mistyped name included) likewise lands in ``model_extra``.

    Attributes:
        id: Unique identifier for the entity
        resource_type: Type of the entity (e.g., "UserStory", "Bug", "User")
        create_date: When the entity was created (optional)
        modify_date: When the entity was last modified (optional)
        custom_fields: Custom-field values embedded in the entity's
            ``CustomFields`` array (present when fetched via ``include=``)
    """

    model_config = ConfigDict(
        populate_by_name=True,  # Allow both alias and field name
        str_strip_whitespace=True,  # Strip whitespace from strings
        validate_assignment=True,  # Validate on assignment
        extra="allow",  # Preserve undeclared API fields in model_extra
    )

    id: int = Field(alias="Id", description="Unique identifier")
    resource_type: str | None = Field(default=None, alias="ResourceType", description="Entity type")
    create_date: TPDateTime | None = Field(
        default=None, alias="CreateDate", description="Creation timestamp"
    )
    modify_date: TPDateTime | None = Field(
        default=None, alias="ModifyDate", description="Modification timestamp"
    )
    custom_fields: list[CustomFieldValue] | None = Field(
        default=None, alias="CustomFields", description="Custom-field values"
    )

    # Property accessors for PascalCase access
    @property
    def Id(self) -> int:
        """Access id field via PascalCase (API format)."""
        return self.id

    @property
    def ResourceType(self) -> str | None:
        """Access resource_type field via PascalCase (API format)."""
        return self.resource_type

    @property
    def CreateDate(self) -> datetime | None:
        """Access create_date field via PascalCase (API format)."""
        return self.create_date

    @property
    def ModifyDate(self) -> datetime | None:
        """Access modify_date field via PascalCase (API format)."""
        return self.modify_date

    @property
    def CustomFields(self) -> list[CustomFieldValue] | None:
        """Access custom_fields field via PascalCase (API format)."""
        return self.custom_fields


class NamedEntity(Entity):
    """Base class for TP entities that carry a display Name.

    The common shape - most domain entities have a ``Name``. Which types do
    not, and why, is stated once on :class:`Entity`.

    Attributes:
        name: Display name of the entity
    """

    name: str | None = Field(default=None, alias="Name", description="Display name")

    @property
    def Name(self) -> str | None:
        """Access name field via PascalCase (API format)."""
        return self.name


class GeneralEntity(NamedEntity):
    """TP's ``General`` base - the shape shared by every domain entity.

    ``Project``, ``Team``, ``Release``, ``Iteration``, ``TeamIteration`` and
    ``TestCase`` derive from this directly; the work-item types reach it
    through :class:`AssignableEntity`.

    The four ``GeneralUser``-shaped references (``Owner``, ``Creator``,
    ``LastEditor``, ``LastCommentedUser``) arrive as :class:`UserRef` - TP
    sends them with ``FirstName``/``LastName``/``Login``/``FullName`` and no
    ``Name`` key. ``Owner`` records who *created* the entity, not who is
    working it: for a work item that is the ``Assignment`` collection (see
    ``client.assignments``).

    Attributes:
        description: Detailed description
        start_date: Start date/time
        end_date: End date/time
        last_comment_date: When the entity was last commented on
        tags: Comma-separated tag string (TP stores tags as one string)
        numeric_priority: TP's global ordering rank (a float, not a Priority)
        entity_version: Per-record version counter (increments on every edit)
        is_now: Whether the entity sits in the current time window
        is_next: Whether the entity sits in the next time window
        is_previous: Whether the entity sits in the previous time window
        entity_type: The TP entity type this record is an instance of
        owner: Who created the entity (TP deprecates this in favour of creator)
        creator: Who created the entity
        last_editor: Who last modified the entity
        last_commented_user: Who last commented on the entity
        project: Project reference
        linked_test_plan: Linked test plan reference
        milestone: Milestone reference
    """

    # Content
    description: str | None = Field(
        default=None, alias="Description", description="Detailed description"
    )
    tags: str | None = Field(default=None, alias="Tags", description="Comma-separated tags")

    # Date tracking
    start_date: TPDateTime | None = Field(
        default=None, alias="StartDate", description="Start date/time"
    )
    end_date: TPDateTime | None = Field(default=None, alias="EndDate", description="End date/time")
    last_comment_date: TPDateTime | None = Field(
        default=None, alias="LastCommentDate", description="Last comment date/time"
    )

    # Ordering / versioning
    numeric_priority: float | None = Field(
        default=None, alias="NumericPriority", description="Global ordering rank"
    )
    entity_version: int | None = Field(
        default=None, alias="EntityVersion", description="Per-record version counter"
    )

    # Time-window flags
    is_now: bool | None = Field(default=None, alias="IsNow", description="In the current window")
    is_next: bool | None = Field(default=None, alias="IsNext", description="In the next window")
    is_previous: bool | None = Field(
        default=None, alias="IsPrevious", description="In the previous window"
    )

    # Relationships
    entity_type: EntityTypeRef | None = Field(
        default=None, alias="EntityType", description="TP entity type"
    )
    owner: UserRef | None = Field(default=None, alias="Owner", description="Creator (deprecated)")
    creator: UserRef | None = Field(default=None, alias="Creator", description="Creator")
    last_editor: UserRef | None = Field(
        default=None, alias="LastEditor", description="Last modifier"
    )
    last_commented_user: UserRef | None = Field(
        default=None, alias="LastCommentedUser", description="Last commenter"
    )
    project: EntityRef | None = Field(default=None, alias="Project", description="Project")
    linked_test_plan: EntityRef | None = Field(
        default=None, alias="LinkedTestPlan", description="Linked test plan"
    )
    milestone: EntityRef | None = Field(default=None, alias="Milestone", description="Milestone")


class AssignableEntity(GeneralEntity):
    """TP's ``Assignable`` base - the work-item shape.

    ``UserStory``, ``Bug``, ``Task``, ``Feature``, ``Epic`` and ``Request``
    derive from this. It adds the effort/time surface, the planning
    references, and the workflow state that make a record schedulable.

    Two fields read as a priority and are not interchangeable: ``priority`` is
    the entity-type-scoped ``Priority`` record (arriving with an
    ``Importance``), while ``numeric_priority`` on :class:`GeneralEntity` is
    TP's continuous backlog-ordering rank.

    ``team`` is deprecated upstream - TP's ``/meta`` marks it so, and
    ``responsible_team`` (a ``TeamAssignment`` reference) is the current
    surface - but it is still populated and still declared here.

    The numeric fields carry no range constraint. TP computes most of them and
    documents no bounds, and a constraint on a server-supplied value fails the
    **whole entity**, not the field: one out-of-range roll-up would abort a
    whole ``list()`` page with a ``ParseError``. A read model that faithfully
    reports what TP sent is worth more than one that asserts an invariant the
    API never promised. Write-side range checks belong where the value
    originates - see ``times.upsert``, which validates before sending.

    Attributes:
        effort: Total effort estimate
        effort_completed: Completed effort
        effort_todo: Remaining effort
        progress: Completion ratio TP derives from effort (0.0 - 1.0)
        time_spent: Hours logged against the item
        time_remain: Hours still expected
        units: The unit effort is expressed in (e.g. "h", "pt")
        lead_time: Days from creation to completion
        cycle_time: Days from work starting to completion
        last_state_change_date: When the entity state last changed
        planned_start_date: Planned start (shadows the assigned iteration)
        planned_end_date: Planned end (shadows the assigned iteration)
        forecast_end_date: TP's projected completion date
        entity_state: Current workflow state reference
        priority: Priority reference, scoped to this entity type
        release: Release reference
        iteration: Iteration reference
        team_iteration: TeamIteration (team sprint) reference
        team: Team reference (deprecated upstream)
        responsible_team: TeamAssignment reference
        assigned_user: Assigned users
    """

    # Effort / time tracking
    effort: float | None = Field(default=None, alias="Effort", description="Total effort")
    effort_completed: float | None = Field(
        default=None, alias="EffortCompleted", description="Completed effort"
    )
    effort_todo: float | None = Field(
        default=None, alias="EffortToDo", description="Remaining effort"
    )
    time_spent: float | None = Field(default=None, alias="TimeSpent", description="Time spent")
    time_remain: float | None = Field(
        default=None, alias="TimeRemain", description="Time remaining"
    )
    progress: float | None = Field(default=None, alias="Progress", description="Completion ratio")
    units: str | None = Field(default=None, alias="Units", description="Effort unit")

    # Flow metrics
    lead_time: float | None = Field(default=None, alias="LeadTime", description="Lead time (days)")
    cycle_time: float | None = Field(
        default=None, alias="CycleTime", description="Cycle time (days)"
    )

    # Date tracking
    last_state_change_date: TPDateTime | None = Field(
        default=None, alias="LastStateChangeDate", description="Last state change"
    )
    planned_start_date: TPDateTime | None = Field(
        default=None, alias="PlannedStartDate", description="Planned start"
    )
    planned_end_date: TPDateTime | None = Field(
        default=None, alias="PlannedEndDate", description="Planned end"
    )
    forecast_end_date: TPDateTime | None = Field(
        default=None, alias="ForecastEndDate", description="Forecast end"
    )

    # Relationships
    entity_state: EntityRef | None = Field(
        default=None, alias="EntityState", description="Workflow state"
    )
    priority: RefWithImportance | None = Field(
        default=None, alias="Priority", description="Priority"
    )
    release: EntityRef | None = Field(default=None, alias="Release", description="Release")
    iteration: EntityRef | None = Field(default=None, alias="Iteration", description="Iteration")
    team_iteration: EntityRef | None = Field(
        default=None, alias="TeamIteration", description="Team iteration"
    )
    team: EntityRef | None = Field(
        default=None, alias="Team", description="Team (deprecated upstream)"
    )
    responsible_team: EntityRef | None = Field(
        default=None, alias="ResponsibleTeam", description="Responsible team assignment"
    )

    # Collections
    assigned_user: AssignedUsers | None = Field(
        default=None, alias="AssignedUser", description="Assigned users"
    )
