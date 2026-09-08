"""The six ``Assignable`` work-item types.

Everything these share - effort, flow metrics, planning references, workflow
state, assigned users - is declared once on
:class:`targetprocess._base.AssignableEntity`. Each class below adds only what
TP's ``/meta`` declares beyond that base for its own type. ``InitialEstimate``
and ``Build`` recur but are deliberately not on the base: TP gives Task and Bug
no ``InitialEstimate``, and Task no ``Build``.

Re-exported by :mod:`targetprocess.models`, which stays the import surface
callers use.
"""

from pydantic import Field

from targetprocess._base import AssignableEntity
from targetprocess._nested import EntityRef, RefWithImportance


class UserStory(AssignableEntity):
    """User story entity in agile workflows.

    The central work item: a requirement sized in effort, placed in a release
    and iteration, and worked by an assigned team. Adds a ``Feature`` parent to
    the assignable base.

    Attributes:
        initial_estimate: Effort at the point the story was first estimated
        feature: Parent feature reference
        build: Build reference
    """

    initial_estimate: float | None = Field(
        default=None, alias="InitialEstimate", description="Initial effort"
    )
    feature: EntityRef | None = Field(default=None, alias="Feature", description="Parent feature")
    build: EntityRef | None = Field(default=None, alias="Build", description="Build")


class Bug(AssignableEntity):
    """Bug/defect entity.

    Adds a ``Severity`` alongside the inherited ``Priority`` - TP ranks a bug
    on both axes, each an ``{Id, Name, Importance}`` reference - and the
    ``UserStory``/``Feature`` the defect was found against.

    Attributes:
        severity: Severity reference (e.g. {Name: "Blocking", Importance: 1})
        user_story: Parent user story reference
        feature: Parent feature reference
        build: Build reference
    """

    severity: RefWithImportance | None = Field(
        default=None, alias="Severity", description="Severity"
    )
    user_story: EntityRef | None = Field(
        default=None, alias="UserStory", description="Parent user story"
    )
    feature: EntityRef | None = Field(default=None, alias="Feature", description="Parent feature")
    build: EntityRef | None = Field(default=None, alias="Build", description="Build")


class Task(AssignableEntity):
    """Task entity for work breakdown.

    The finest-grained work item: a step under a ``UserStory``. Alone among the
    assignables it carries neither an ``InitialEstimate`` nor a ``Build``.

    ``parent`` is not declared in TP's ``/meta`` for Task but is queryable and
    returns the owning ``Assignable``; ``user_story`` is the documented
    reference and the one to prefer.

    Attributes:
        user_story: Parent user story reference
        parent: Parent entity reference (undocumented; prefer user_story)
    """

    user_story: EntityRef | None = Field(
        default=None, alias="UserStory", description="Parent user story"
    )
    parent: EntityRef | None = Field(default=None, alias="Parent", description="Parent entity")


class Feature(AssignableEntity):
    """Feature entity for product capabilities.

    A capability grouping user stories, itself rolled up under an ``Epic`` or
    ``PortfolioEpic``.

    Attributes:
        initial_estimate: Effort at the point the feature was first estimated
        business_value: Business value
        epic: Parent epic reference
        portfolio_epic: Parent portfolio epic reference
        build: Build reference
    """

    initial_estimate: float | None = Field(
        default=None, alias="InitialEstimate", description="Initial effort"
    )
    business_value: int | None = Field(
        default=None, alias="BusinessValue", description="Business value"
    )
    epic: EntityRef | None = Field(default=None, alias="Epic", description="Parent epic")
    portfolio_epic: EntityRef | None = Field(
        default=None, alias="PortfolioEpic", description="Parent portfolio epic"
    )
    build: EntityRef | None = Field(default=None, alias="Build", description="Build")


class Epic(AssignableEntity):
    """Epic entity for large initiatives.

    Groups features under a single initiative, itself rolled up under a
    ``PortfolioEpic``.

    Attributes:
        initial_estimate: Effort at the point the epic was first estimated
        business_value: Business value
        portfolio_epic: Parent portfolio epic reference
        build: Build reference
    """

    initial_estimate: float | None = Field(
        default=None, alias="InitialEstimate", description="Initial effort"
    )
    business_value: int | None = Field(
        default=None, alias="BusinessValue", description="Business value"
    )
    portfolio_epic: EntityRef | None = Field(
        default=None, alias="PortfolioEpic", description="Parent portfolio epic"
    )
    build: EntityRef | None = Field(default=None, alias="Build", description="Build")


class Request(AssignableEntity):
    """Request entity for feature/change requests.

    The inbound-facing assignable: raised by a requester rather than planned,
    so it carries a source, a reply flag, a privacy flag and a vote count that
    the other work-item types have no use for.

    Attributes:
        source_type: How the request arrived (e.g. "None", "Email", "Portal")
        is_replied: Whether the requester has had a reply
        is_private: Whether the request is hidden from the requester portal
        votes_count: Number of votes the request has attracted
        request_type: Request-type reference (e.g. "Enhancement")
        build: Build reference
    """

    source_type: str | None = Field(default=None, alias="SourceType", description="Request source")
    is_replied: bool | None = Field(
        default=None, alias="IsReplied", description="Whether replied to"
    )
    is_private: bool | None = Field(default=None, alias="IsPrivate", description="Whether private")
    votes_count: int | None = Field(default=None, alias="VotesCount", description="Vote count")
    request_type: EntityRef | None = Field(
        default=None, alias="RequestType", description="Request type"
    )
    build: EntityRef | None = Field(default=None, alias="Build", description="Build")
