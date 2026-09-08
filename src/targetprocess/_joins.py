"""The join entities that connect two records rather than describing one.

``Assignment``, ``TeamAssignment``, ``RoleEffort``, ``Relation`` and ``Time``
each pair an ``Assignable`` with a user, team, role or another entity. None
carries a ``Name``, and none sits in TP's ``General`` hierarchy, so all extend
:class:`targetprocess._base.Entity` directly.

Re-exported by :mod:`targetprocess.models`, which stays the import surface
callers use.
"""

from pydantic import Field

from targetprocess._base import Entity
from targetprocess._dates import TPDateTime
from targetprocess._nested import EntityRef, UserRef


class Assignment(Entity):
    """User-to-work-item role assignment (join entity).

    Pairs a user (``GeneralUser``) with a ``Role`` on an ``Assignable`` -
    the authoritative record of who is assigned to a work item and in which
    capacity (``Owner`` only records who created it).

    Attributes:
        general_user: Assigned user reference
        role: Role reference
        assignable: Assignable (work item) reference
    """

    general_user: UserRef | None = Field(
        default=None, alias="GeneralUser", description="Assigned user"
    )
    role: EntityRef | None = Field(default=None, alias="Role", description="Role")
    assignable: EntityRef | None = Field(
        default=None, alias="Assignable", description="Assignable (work item)"
    )


class TeamAssignment(Entity):
    """Team-to-work-item assignment (join entity).

    Assigns a Team to an Assignable over a time window, carrying the
    assignment's entity state.

    Attributes:
        start_date: Assignment start date/time
        end_date: Assignment end date/time
        team: Team reference
        assignable: Assignable (work item) reference
        entity_state: Workflow state reference
    """

    # Date tracking
    start_date: TPDateTime | None = Field(
        default=None, alias="StartDate", description="Start date/time"
    )
    end_date: TPDateTime | None = Field(default=None, alias="EndDate", description="End date/time")

    # Relationships
    team: EntityRef | None = Field(default=None, alias="Team", description="Team")
    assignable: EntityRef | None = Field(
        default=None, alias="Assignable", description="Assignable (work item)"
    )
    entity_state: EntityRef | None = Field(
        default=None, alias="EntityState", description="Workflow state"
    )


class RoleEffort(Entity):
    """Per-role effort allocation on an Assignable (join entity).

    Breaks an Assignable's effort down by Role.

    Attributes:
        initial_estimate: Initial effort estimate >= 0
        effort: Total effort >= 0
        effort_completed: Completed effort >= 0
        effort_todo: Remaining effort >= 0
        time_spent: Time spent >= 0
        time_remain: Time remaining >= 0
        assignable: Assignable (work item) reference
        role: Role reference
    """

    # Effort / time tracking
    initial_estimate: float | None = Field(
        default=None, alias="InitialEstimate", ge=0, description="Initial estimate"
    )
    effort: float | None = Field(default=None, alias="Effort", ge=0, description="Total effort")
    effort_completed: float | None = Field(
        default=None, alias="EffortCompleted", ge=0, description="Completed effort"
    )
    effort_todo: float | None = Field(
        default=None, alias="EffortToDo", ge=0, description="Remaining effort"
    )
    time_spent: float | None = Field(
        default=None, alias="TimeSpent", ge=0, description="Time spent"
    )
    time_remain: float | None = Field(
        default=None, alias="TimeRemain", ge=0, description="Time remaining"
    )

    # Relationships
    assignable: EntityRef | None = Field(
        default=None, alias="Assignable", description="Assignable (work item)"
    )
    role: EntityRef | None = Field(default=None, alias="Role", description="Role")


class Relation(Entity):
    """Entity-to-entity relation (join entity).

    Links two entities, typed by a ``RelationType`` (Dependency, Blocker,
    Relation, Duplicate, ...). The direction carries meaning: the source is the
    origin of the dependency - in a Blocker relation the source is the blocking
    item and the target the blocked one.

    TP exposes the same pair twice. ``Master``/``Slave`` are the original names
    and are marked deprecated in ``/meta``; ``Inbound``/``Outbound`` are the
    current ones. They are the same two records - ``Inbound`` mirrors
    ``Master`` and ``Outbound`` mirrors ``Slave`` - so prefer the latter pair in
    new code.

    Attributes:
        inbound: Source entity reference
        outbound: Target entity reference
        master: Source entity reference (deprecated upstream; prefer inbound)
        slave: Target entity reference (deprecated upstream; prefer outbound)
        relation_type: Relation-type reference
    """

    # Relationships
    inbound: EntityRef | None = Field(default=None, alias="Inbound", description="Source entity")
    outbound: EntityRef | None = Field(default=None, alias="Outbound", description="Target entity")
    master: EntityRef | None = Field(
        default=None, alias="Master", description="Source entity (deprecated upstream)"
    )
    slave: EntityRef | None = Field(
        default=None, alias="Slave", description="Target entity (deprecated upstream)"
    )
    relation_type: EntityRef | None = Field(
        default=None, alias="RelationType", description="Relation type"
    )


class Time(Entity):
    """Time entry logged against an Assignable (join entity).

    Records spent and remaining hours for a User against an Assignable on a
    given date.

    ``assignable`` is the general reference; TP additionally exposes a narrower
    back-reference per work-item type, of which exactly one is populated for
    any given entry (a ``CustomActivity`` entry, for instance, has a null
    ``assignable``). They are declared so an entry's origin is readable without
    a second fetch.

    Attributes:
        spent: Hours spent >= 0
        remain: Hours remaining >= 0
        is_estimation: Entry records an estimate rather than actual time
        date: Date/time the work is logged against
        description: Free-text description of the work
        assignable: Assignable (work item) reference
        user: User the time is logged for
        project: Project reference (TP derives it from the Assignable)
        role: Role reference
        user_story: User story the entry was logged against, if any
        task: Task the entry was logged against, if any
        bug: Bug the entry was logged against, if any
        request: Request the entry was logged against, if any
        test_plan: Test plan the entry was logged against, if any
        test_plan_run: Test plan run the entry was logged against, if any
        custom_activity: Custom activity the entry was logged against, if any
    """

    # Effort / time tracking
    spent: float | None = Field(default=None, alias="Spent", ge=0, description="Hours spent")
    remain: float | None = Field(default=None, alias="Remain", ge=0, description="Hours remaining")
    is_estimation: bool | None = Field(
        default=None, alias="IsEstimation", description="Entry is an estimation"
    )

    # Date tracking
    date: TPDateTime | None = Field(default=None, alias="Date", description="Date/time logged")

    # Content
    description: str | None = Field(default=None, alias="Description", description="Description")

    # Relationships
    assignable: EntityRef | None = Field(
        default=None, alias="Assignable", description="Assignable (work item)"
    )
    user: UserRef | None = Field(default=None, alias="User", description="User")
    project: EntityRef | None = Field(default=None, alias="Project", description="Project")
    role: EntityRef | None = Field(default=None, alias="Role", description="Role")

    # Narrow back-references: at most one is populated per entry.
    user_story: EntityRef | None = Field(
        default=None, alias="UserStory", description="User story logged against"
    )
    task: EntityRef | None = Field(default=None, alias="Task", description="Task logged against")
    bug: EntityRef | None = Field(default=None, alias="Bug", description="Bug logged against")
    request: EntityRef | None = Field(
        default=None, alias="Request", description="Request logged against"
    )
    test_plan: EntityRef | None = Field(
        default=None, alias="TestPlan", description="Test plan logged against"
    )
    test_plan_run: EntityRef | None = Field(
        default=None, alias="TestPlanRun", description="Test plan run logged against"
    )
    custom_activity: EntityRef | None = Field(
        default=None, alias="CustomActivity", description="Custom activity logged against"
    )
