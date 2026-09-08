"""The ``General`` types that are not work items.

``Project``, ``Team``, ``Release``, ``Iteration``, ``TeamIteration`` and
``TestCase`` derive from TP's ``General`` base but not from ``Assignable``, so
they inherit :class:`targetprocess._base.GeneralEntity` and declare their own
effort and planning fields rather than the assignable set.

Several carry ``Effort``/``EffortCompleted``/``EffortToDo``/``Progress``/
``Units`` as roll-ups of the work items inside them, identically. They are
repeated per class rather than hoisted into a shared mixin because TP declares
no such base: the grouping would be this library's invention, and the next type
to gain or lose one of the five would have to be pulled back out of it. The
repetition is the cost of each class listing exactly what its own ``/meta``
declares, which is the property ``scripts/check_model_coverage.py`` checks.

Re-exported by :mod:`targetprocess.models`, which stays the import surface
callers use.
"""

from pydantic import Field

from targetprocess._base import GeneralEntity
from targetprocess._dates import TPDateTime
from targetprocess._nested import AssignedUsers, EntityRef, RefWithImportance


class Project(GeneralEntity):
    """Project entity for organisational structure.

    The container every other entity hangs off. Carries its own workflow state
    and process, the effort roll-up of the work inside it, and the branding
    fields TP renders in the project picker.

    Attributes:
        effort: Rolled-up effort
        effort_completed: Rolled-up completed effort
        effort_todo: Rolled-up remaining effort
        progress: Completion ratio derived from effort (0.0 - 1.0)
        units: The unit effort is expressed in (e.g. "h", "pt")
        is_active: Whether the project is active
        is_product: Whether the project is a product rather than a project
        is_private: Whether the project is hidden from non-members
        abbreviation: Short code TP renders in compact views
        mail_reply_address: Address inbound request email is accepted on
        color: Project colour TP renders in the UI
        planned_start_date: Planned start date/time
        planned_end_date: Planned end date/time
        last_state_change_date: When the entity state last changed
        forecast_end_date: TP's projected completion date
        anticipated_end_date: Manually anticipated completion date
        lead_time: Days from creation to completion
        cycle_time: Days from work starting to completion
        entity_state: Current workflow state reference
        process: Process (workflow definition) reference
        program: Program reference
        company: Company reference
    """

    # Effort roll-up
    effort: float | None = Field(default=None, alias="Effort", description="Rolled-up effort")
    effort_completed: float | None = Field(
        default=None, alias="EffortCompleted", description="Completed effort"
    )
    effort_todo: float | None = Field(
        default=None, alias="EffortToDo", description="Remaining effort"
    )
    progress: float | None = Field(default=None, alias="Progress", description="Completion ratio")
    units: str | None = Field(default=None, alias="Units", description="Effort unit")

    # Flags and branding
    is_active: bool | None = Field(default=None, alias="IsActive", description="Active status")
    is_product: bool | None = Field(default=None, alias="IsProduct", description="Is a product")
    is_private: bool | None = Field(default=None, alias="IsPrivate", description="Is private")
    abbreviation: str | None = Field(
        default=None, alias="Abbreviation", description="Short project code"
    )
    mail_reply_address: str | None = Field(
        default=None, alias="MailReplyAddress", description="Inbound mail address"
    )
    color: str | None = Field(default=None, alias="Color", description="Display colour")

    # Date tracking
    planned_start_date: TPDateTime | None = Field(
        default=None, alias="PlannedStartDate", description="Planned start"
    )
    planned_end_date: TPDateTime | None = Field(
        default=None, alias="PlannedEndDate", description="Planned end"
    )
    last_state_change_date: TPDateTime | None = Field(
        default=None, alias="LastStateChangeDate", description="Last state change"
    )
    forecast_end_date: TPDateTime | None = Field(
        default=None, alias="ForecastEndDate", description="Forecast end"
    )
    anticipated_end_date: TPDateTime | None = Field(
        default=None, alias="AnticipatedEndDate", description="Anticipated end"
    )

    # Flow metrics
    lead_time: float | None = Field(default=None, alias="LeadTime", description="Lead time (days)")
    cycle_time: float | None = Field(
        default=None, alias="CycleTime", description="Cycle time (days)"
    )

    # Relationships
    entity_state: EntityRef | None = Field(
        default=None, alias="EntityState", description="Workflow state"
    )
    process: EntityRef | None = Field(default=None, alias="Process", description="Process")
    program: EntityRef | None = Field(default=None, alias="Program", description="Program")
    company: EntityRef | None = Field(default=None, alias="Company", description="Company")


class Team(GeneralEntity):
    """Team entity for organisational structure.

    A bare ``General`` upstream - TP adds only the activity flag and the
    identity TP renders in team pickers.

    Attributes:
        is_active: Whether the team is active
        abbreviation: Short code TP renders in compact views
        emoji_icon: Emoji shorthand TP renders beside the team name
        icon_uri: Path to the team's icon image
        icon: Legacy icon field (deprecated upstream; prefer icon_uri)
    """

    is_active: bool | None = Field(default=None, alias="IsActive", description="Active status")
    abbreviation: str | None = Field(
        default=None, alias="Abbreviation", description="Short team code"
    )
    emoji_icon: str | None = Field(default=None, alias="EmojiIcon", description="Emoji icon")
    icon_uri: str | None = Field(default=None, alias="IconUri", description="Icon image path")
    icon: str | None = Field(
        default=None, alias="Icon", description="Legacy icon (deprecated upstream)"
    )


class Release(GeneralEntity):
    """Release entity for planning and tracking releases.

    A dated window grouping iterations, with the effort roll-up of everything
    scheduled into it. ``start_date`` and ``end_date`` are required upstream.

    Attributes:
        effort: Rolled-up effort
        effort_completed: Rolled-up completed effort
        effort_todo: Rolled-up remaining effort
        progress: Completion ratio derived from effort (0.0 - 1.0)
        units: The unit effort is expressed in (e.g. "h", "pt")
        is_current: Whether this is the current release
        forecast_end_date: TP's projected completion date
        process: Process (workflow definition) reference
    """

    effort: float | None = Field(default=None, alias="Effort", description="Rolled-up effort")
    effort_completed: float | None = Field(
        default=None, alias="EffortCompleted", description="Completed effort"
    )
    effort_todo: float | None = Field(
        default=None, alias="EffortToDo", description="Remaining effort"
    )
    progress: float | None = Field(default=None, alias="Progress", description="Completion ratio")
    units: str | None = Field(default=None, alias="Units", description="Effort unit")
    is_current: bool | None = Field(
        default=None, alias="IsCurrent", description="Is the current release"
    )
    forecast_end_date: TPDateTime | None = Field(
        default=None, alias="ForecastEndDate", description="Forecast end"
    )
    process: EntityRef | None = Field(default=None, alias="Process", description="Process")


class Iteration(GeneralEntity):
    """Iteration entity for agile sprints.

    A project-level sprint inside a ``Release``. TP scopes iterations to the
    release, not to a team - the team-scoped equivalent is
    :class:`TeamIteration`.

    Attributes:
        effort: Rolled-up effort
        effort_completed: Rolled-up completed effort
        effort_todo: Rolled-up remaining effort
        progress: Completion ratio derived from effort (0.0 - 1.0)
        units: The unit effort is expressed in (e.g. "h", "pt")
        velocity: Effort completed per unit time
        duration: Iteration length in days
        is_current: Whether this is the current iteration
        can_be_finished: Whether TP will allow the iteration to be closed
        forecast_end_date: TP's projected completion date
        release: Release reference
    """

    effort: float | None = Field(default=None, alias="Effort", description="Rolled-up effort")
    effort_completed: float | None = Field(
        default=None, alias="EffortCompleted", description="Completed effort"
    )
    effort_todo: float | None = Field(
        default=None, alias="EffortToDo", description="Remaining effort"
    )
    progress: float | None = Field(default=None, alias="Progress", description="Completion ratio")
    units: str | None = Field(default=None, alias="Units", description="Effort unit")
    velocity: float | None = Field(default=None, alias="Velocity", description="Velocity")
    duration: int | None = Field(default=None, alias="Duration", description="Length in days")
    is_current: bool | None = Field(
        default=None, alias="IsCurrent", description="Is the current iteration"
    )
    can_be_finished: bool | None = Field(
        default=None, alias="CanBeFinished", description="Can be closed"
    )
    forecast_end_date: TPDateTime | None = Field(
        default=None, alias="ForecastEndDate", description="Forecast end"
    )
    release: EntityRef | None = Field(default=None, alias="Release", description="Release")

    # Not declared in TP's /meta for Iteration and rejected by include= there;
    # kept because removing a published field would break callers. The
    # team-scoped sprint is TeamIteration.
    team: EntityRef | None = Field(
        default=None, alias="Team", description="Team (absent upstream; prefer TeamIteration)"
    )


class TeamIteration(GeneralEntity):
    """Team-specific iteration (sprint) entity.

    In TP each team owns its own iterations; a TeamIteration carries the
    team's sprint window, effort/velocity/capacity, and its Release.

    Attributes:
        effort: Rolled-up effort
        effort_completed: Rolled-up completed effort
        effort_todo: Rolled-up remaining effort
        progress: Completion ratio derived from effort (0.0 - 1.0)
        units: The unit effort is expressed in (e.g. "h", "pt")
        velocity: Effort completed per unit time
        capacity: Effort the team can absorb in the window
        duration: Iteration length in days
        is_current: Whether this is the team's current iteration
        can_be_finished: Whether TP will allow the iteration to be closed
        forecast_end_date: TP's projected completion date
        team: Team reference
        release: Release reference
    """

    effort: float | None = Field(default=None, alias="Effort", description="Rolled-up effort")
    effort_completed: float | None = Field(
        default=None, alias="EffortCompleted", description="Completed effort"
    )
    effort_todo: float | None = Field(
        default=None, alias="EffortToDo", description="Remaining effort"
    )
    progress: float | None = Field(default=None, alias="Progress", description="Completion ratio")
    units: str | None = Field(default=None, alias="Units", description="Effort unit")
    velocity: float | None = Field(default=None, alias="Velocity", description="Team velocity")
    capacity: float | None = Field(default=None, alias="Capacity", description="Team capacity")
    duration: int | None = Field(default=None, alias="Duration", description="Length in days")
    is_current: bool | None = Field(
        default=None, alias="IsCurrent", description="Is the current iteration"
    )
    can_be_finished: bool | None = Field(
        default=None, alias="CanBeFinished", description="Can be closed"
    )
    forecast_end_date: TPDateTime | None = Field(
        default=None, alias="ForecastEndDate", description="Forecast end"
    )
    team: EntityRef | None = Field(default=None, alias="Team", description="Team")
    release: EntityRef | None = Field(default=None, alias="Release", description="Release")


class TestCase(GeneralEntity):
    """TestCase entity for quality assurance.

    A ``General`` rather than an ``Assignable``: a test case has no effort, no
    iteration and no workflow state - its status is the outcome of its last
    run.

    Attributes:
        last_run_status: Outcome of the most recent run (e.g. "Passed")
        last_run_date: When the test case was last run
        last_failure_comment: Comment recorded against the last failure
        last_status: Legacy boolean pass flag (deprecated; prefer last_run_status)
        steps: Legacy free-text steps (deprecated upstream)
        success: Legacy free-text expected result (deprecated upstream)
        priority: Priority reference, scoped to this entity type
        user_story: Parent user story reference (deprecated upstream)
    """

    last_run_status: str | None = Field(
        default=None, alias="LastRunStatus", description="Last run outcome"
    )
    last_run_date: TPDateTime | None = Field(
        default=None, alias="LastRunDate", description="Last run date/time"
    )
    last_failure_comment: str | None = Field(
        default=None, alias="LastFailureComment", description="Last failure comment"
    )
    last_status: bool | None = Field(
        default=None, alias="LastStatus", description="Legacy pass flag (deprecated upstream)"
    )
    steps: str | None = Field(
        default=None, alias="Steps", description="Legacy steps (deprecated upstream)"
    )
    success: str | None = Field(
        default=None, alias="Success", description="Legacy expected result (deprecated upstream)"
    )
    priority: RefWithImportance | None = Field(
        default=None, alias="Priority", description="Priority"
    )
    user_story: EntityRef | None = Field(
        default=None,
        alias="UserStory",
        description="Parent user story (deprecated upstream)",
    )

    # Neither is declared in TP's /meta for TestCase, and include= rejects both
    # there; kept because removing a published field would break callers.
    entity_state: EntityRef | None = Field(
        default=None, alias="EntityState", description="Workflow state (absent upstream)"
    )
    assigned_user: AssignedUsers | None = Field(
        default=None, alias="AssignedUser", description="Assigned users (absent upstream)"
    )
