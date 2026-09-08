"""The lookup, configuration and people types outside TP's ``General`` hierarchy.

``User`` derives from ``GeneralUser`` upstream; ``EntityState``, ``Priority``,
``Role``, ``RelationType``, ``Severity``, ``Process``, ``Workflow``,
``EntityType``, ``Term``, ``CustomActivity`` and ``CustomRule`` derive from
nothing at all. None of them carry the ``General`` field set, so they extend
:class:`targetprocess._base.Entity` or :class:`targetprocess._base.NamedEntity`
directly.

Re-exported by :mod:`targetprocess.models`, which stays the import surface
callers use.
"""

from pydantic import Field

from targetprocess._base import Entity, NamedEntity
from targetprocess._dates import TPDateTime
from targetprocess._nested import EntityRef, EntityTypeRef, UserRef


class User(Entity):
    """User entity for people and authentication.

    Unlike every other entity, User carries no ``Name`` field - identity is
    expressed via ``FirstName``/``LastName``/``Login``/``FullName`` instead.

    The allocation fields describe capacity planning: ``weekly_available_hours``
    is the contracted week, ``current_allocation`` the percentage already
    committed, and the ``available_future_*`` pair the same measures projected
    forward.

    TP declares one further property, ``Password``, which it marks unreadable
    (``CanGet: false``). It is deliberately not declared: it never arrives in a
    response, and a password-shaped attribute would otherwise appear in every
    ``model_dump``. Set it through ``users.update(id, Password=...)``, which
    passes fields through verbatim.

    Attributes:
        email: User email address
        first_name: User first name
        last_name: User last name
        login: User login
        full_name: User full name
        is_active: Whether the user is active
        is_administrator: Whether the user is an administrator
        is_observer: Whether the user is a read-only observer
        is_contributor: Whether the user is a contributor
        is_integration: Whether the account is a service/integration account
        kind: Account kind (e.g. "User", "Requester")
        locale: User locale
        rich_editor: Editor the user writes in (e.g. "Markdown")
        avatar_uri: Path to the user's avatar image
        global_id: TP's cross-instance identifier
        entity_version: Per-record version counter (increments on every edit)
        delete_date: When the account was deleted (None while active)
        last_login_date: When the user last signed in
        access_start_date: Start of the account's access window
        access_end_date: End of the account's access window
        weekly_available_hours: Contracted hours per week
        current_allocation: Percentage of capacity already committed
        current_available_hours: Hours still uncommitted
        available_from: Date the user next has capacity
        available_future_allocation: Projected committed percentage
        available_future_hours: Projected uncommitted hours
        password_hash_algorithm: Algorithm the stored password hash uses
        frontdoor_user_id: Identifier in TP's identity service
        frontdoor_user_roles: Roles held in TP's identity service
        active_directory_name: Directory account name, when AD-linked
        legacy_skills: Free-text skills field retained from older TP versions
        role: User role reference
    """

    # Identity
    email: str | None = Field(default=None, alias="Email", description="Email address")
    first_name: str | None = Field(default=None, alias="FirstName", description="First name")
    last_name: str | None = Field(default=None, alias="LastName", description="Last name")
    login: str | None = Field(default=None, alias="Login", description="Login")
    full_name: str | None = Field(default=None, alias="FullName", description="Full name")
    avatar_uri: str | None = Field(default=None, alias="AvatarUri", description="Avatar path")
    global_id: str | None = Field(default=None, alias="GlobalId", description="Cross-instance id")

    # Account flags
    is_active: bool | None = Field(default=None, alias="IsActive", description="Active status")
    is_administrator: bool | None = Field(
        default=None, alias="IsAdministrator", description="Administrator"
    )
    is_observer: bool | None = Field(default=None, alias="IsObserver", description="Observer")
    is_contributor: bool | None = Field(
        default=None, alias="IsContributor", description="Contributor"
    )
    is_integration: bool | None = Field(
        default=None, alias="IsIntegration", description="Service account"
    )
    kind: str | None = Field(default=None, alias="Kind", description="Account kind")
    locale: str | None = Field(default=None, alias="Locale", description="Locale")
    rich_editor: str | None = Field(default=None, alias="RichEditor", description="Editor type")
    entity_version: int | None = Field(
        default=None, alias="EntityVersion", description="Per-record version counter"
    )

    # Date tracking
    delete_date: TPDateTime | None = Field(
        default=None, alias="DeleteDate", description="Deletion timestamp"
    )
    last_login_date: TPDateTime | None = Field(
        default=None, alias="LastLoginDate", description="Last sign-in"
    )
    access_start_date: TPDateTime | None = Field(
        default=None, alias="AccessStartDate", description="Access window start"
    )
    access_end_date: TPDateTime | None = Field(
        default=None, alias="AccessEndDate", description="Access window end"
    )
    available_from: TPDateTime | None = Field(
        default=None, alias="AvailableFrom", description="Next available from"
    )

    # Capacity
    weekly_available_hours: float | None = Field(
        default=None, alias="WeeklyAvailableHours", description="Contracted weekly hours"
    )
    current_allocation: int | None = Field(
        default=None, alias="CurrentAllocation", description="Committed capacity (%)"
    )
    current_available_hours: float | None = Field(
        default=None, alias="CurrentAvailableHours", description="Uncommitted hours"
    )
    available_future_allocation: int | None = Field(
        default=None, alias="AvailableFutureAllocation", description="Projected committed (%)"
    )
    available_future_hours: float | None = Field(
        default=None, alias="AvailableFutureHours", description="Projected uncommitted hours"
    )

    # Identity provider / directory
    password_hash_algorithm: str | None = Field(
        default=None, alias="PasswordHashAlgorithm", description="Password hash algorithm"
    )
    frontdoor_user_id: str | None = Field(
        default=None, alias="FrontdoorUserId", description="Identity-service id"
    )
    frontdoor_user_roles: str | None = Field(
        default=None, alias="FrontdoorUserRoles", description="Identity-service roles"
    )
    active_directory_name: str | None = Field(
        default=None, alias="ActiveDirectoryName", description="AD account name"
    )
    legacy_skills: str | None = Field(
        default=None, alias="LegacySkills", description="Legacy free-text skills"
    )

    # Relationships
    role: EntityRef | None = Field(default=None, alias="Role", description="User role")


class EntityState(NamedEntity):
    """EntityState entity for workflow states.

    A single column of a ``Workflow``, scoped to one entity type within one
    process. ``numeric_priority`` is what orders the states along the board -
    the ordering TP renders left to right.

    Attributes:
        is_initial: Whether this is an initial state
        is_final: Whether this is a final state
        is_planned: Whether this is a planned state
        is_comment_required: Whether TP requires a comment to enter this state
        numeric_priority: Ordering rank along the workflow
        workflow: Owning workflow reference
        entity_type: Entity type the state applies to (deprecated upstream)
        process: Owning process reference (deprecated upstream)
        parent_entity_state: Parent state, for sub-workflow states
        role: Role the state is restricted to, when restricted
    """

    # State flags
    is_initial: bool | None = Field(
        default=None, alias="IsInitial", description="Initial state flag"
    )
    is_final: bool | None = Field(default=None, alias="IsFinal", description="Final state flag")
    is_planned: bool | None = Field(
        default=None, alias="IsPlanned", description="Planned state flag"
    )
    is_comment_required: bool | None = Field(
        default=None, alias="IsCommentRequired", description="Comment required to enter"
    )
    numeric_priority: float | None = Field(
        default=None, alias="NumericPriority", description="Ordering rank"
    )

    # Relationships
    workflow: EntityRef | None = Field(default=None, alias="Workflow", description="Workflow")
    entity_type: EntityTypeRef | None = Field(
        default=None, alias="EntityType", description="Entity type (deprecated upstream)"
    )
    process: EntityRef | None = Field(
        default=None, alias="Process", description="Process (deprecated upstream)"
    )
    parent_entity_state: EntityRef | None = Field(
        default=None, alias="ParentEntityState", description="Parent state"
    )
    role: EntityRef | None = Field(default=None, alias="Role", description="Restricted-to role")


class Priority(NamedEntity):
    """Priority entity, scoped to a single TP entity type.

    TP defines one priority set per entity type, so a name alone is
    ambiguous instance-wide - "Must Have" is a separate record for
    UserStory, Feature, Epic and PortfolioEpic - while being unique within
    one set. ``entity_type`` is therefore the discriminator that makes a
    name resolve to exactly one record. A Priority carries no Project or
    Process reference: the valid set depends only on the entity type.

    Attributes:
        importance: Rank within the entity type's set (1 is most important)
        is_default: Whether TP applies this priority when none is supplied
        is_most_important: Whether this is the top rank in its set
        entity_type: The entity type this priority belongs to
    """

    importance: int | None = Field(
        default=None, alias="Importance", description="Rank within the entity type's set"
    )
    is_default: bool | None = Field(
        default=None, alias="IsDefault", description="Applied when no priority is supplied"
    )
    is_most_important: bool | None = Field(
        default=None, alias="IsMostImportant", description="Top rank in its set"
    )
    entity_type: EntityTypeRef | None = Field(
        default=None, alias="EntityType", description="Entity type this priority belongs to"
    )


class Role(NamedEntity):
    """Role lookup entity (e.g. Developer, QA Engineer, Product Owner).

    An Assignment pairs a user with a Role, so resolving a role name to its
    Id is what makes assignment payloads constructible. Roles are defined
    instance-wide - unlike :class:`Priority` they are not scoped by entity
    type. The boolean fields are the permissions the role grants.

    Attributes:
        description: Role description
        has_effort: Whether work assigned in this role carries effort
        can_change_owner: Whether the role may reassign an entity's owner
        can_prioritize: Whether the role may reorder the backlog
        can_use_personal_access_tokens: Whether the role may mint access tokens
        time_sheet_access: Whether the role may access timesheets
    """

    description: str | None = Field(
        default=None, alias="Description", description="Role description"
    )
    has_effort: bool | None = Field(default=None, alias="HasEffort", description="Carries effort")
    can_change_owner: bool | None = Field(
        default=None, alias="CanChangeOwner", description="May reassign owner"
    )
    can_prioritize: bool | None = Field(
        default=None, alias="CanPrioritize", description="May reorder the backlog"
    )
    can_use_personal_access_tokens: bool | None = Field(
        default=None,
        alias="CanUsePersonalAccessTokens",
        description="May mint personal access tokens",
    )
    time_sheet_access: bool | None = Field(
        default=None, alias="TimeSheetAccess", description="May access timesheets"
    )


class RelationType(NamedEntity):
    """Relation-type lookup entity (e.g. Dependency, Blocker, Relation, Duplicate).

    The read-only lookup that types a ``Relation``. The API declares only ``Id``
    and ``Name``, so nothing is added beyond :class:`NamedEntity`. Ids are
    instance-specific - resolve a name via ``client.relation_types.resolve``
    rather than hardcoding an Id (one production instance maps Dependency 1,
    Blocker 2, Relation 3, Link 4, Duplicate 5, but another may differ).
    """


class Severity(NamedEntity):
    """Severity lookup entity - how bad a Bug is (e.g. Blocking, Critical, Small).

    TP defines severities instance-wide and only ``Bug`` carries one, so a
    name is unique across the instance - unlike a :class:`Priority`, which
    repeats per entity type - and ``client.severities.resolve`` takes no
    entity type. ``importance`` ranks the set, the minimum value being the
    most severe.

    Attributes:
        importance: Rank within the set (1 is the most severe)
        is_default: Whether TP applies this severity when none is supplied
        is_most_important: Whether this is the most severe rank
        is_least_important: Whether this is the least severe rank
    """

    importance: int | None = Field(
        default=None, alias="Importance", description="Rank within the set"
    )
    is_default: bool | None = Field(
        default=None, alias="IsDefault", description="Applied when no severity is supplied"
    )
    is_most_important: bool | None = Field(
        default=None, alias="IsMostImportant", description="Most severe rank"
    )
    is_least_important: bool | None = Field(
        default=None, alias="IsLeastImportant", description="Least severe rank"
    )


class Process(NamedEntity):
    """Process entity - the practices, terms, workflows and custom fields a Project follows.

    A Project follows exactly one process, and the process is what scopes
    its workflows, custom-field definitions and terms - so a process Id is
    the key for filtering any of those collections.

    One wire name collides here: on a Process, TP's ``CustomFields`` is the
    collection of custom-field *definitions* (an ``Items`` envelope of
    ``CustomField`` records), not the values array ``custom_fields`` holds
    on every entity. A default Process payload carries no such key, so plain
    reads parse; ``client.processes`` refuses ``include=["CustomFields"]``
    with ``ValueError`` before any request rather than failing the parse
    afterwards - list the definitions through ``client.custom_fields``
    filtered by ``Process.Id`` instead.

    Attributes:
        description: Brief description of the process
        is_default: Whether this is the instance default (deprecated upstream)
    """

    description: str | None = Field(
        default=None, alias="Description", description="Process description"
    )
    is_default: bool | None = Field(
        default=None, alias="IsDefault", description="Instance default (deprecated upstream)"
    )


class Workflow(NamedEntity):
    """Workflow entity - the states one entity type moves through in one process.

    A workflow is scoped to a ``Process`` and an ``EntityType``; its columns
    are the :class:`EntityState` records, reachable via
    ``client.entity_states`` filtered by ``Workflow.Id``. A sub-workflow
    hangs off ``parent_workflow``. Names repeat across processes, so there is
    no instance-wide name resolver - filter by process and entity type.

    Attributes:
        process: Owning process reference
        entity_type: Entity type the workflow is defined for
        parent_workflow: Parent workflow, for a sub-workflow
    """

    process: EntityRef | None = Field(default=None, alias="Process", description="Process")
    entity_type: EntityTypeRef | None = Field(
        default=None, alias="EntityType", description="Entity type"
    )
    parent_workflow: EntityRef | None = Field(
        default=None, alias="ParentWorkflow", description="Parent workflow"
    )


class EntityType(NamedEntity):
    """EntityType entity - one of the instance's entity types (Bug, UserStory, ...).

    The instance's own type catalogue, and so the way a client discovers at
    runtime what the instance exposes. TP declares the collection read-only.
    :class:`targetprocess.models.EntityTypeRef` is the *reference* shape other
    entities embed (which can arrive without an ``Id``); this is the full
    record, always identified.

    Attributes:
        custom_field_scope: Scope of custom fields for the type (None,
            Process or Global)
        is_searchable: Whether entities of the type can be searched
        is_unit_in_hour_only: Whether the type measures effort in hours only
        is_assignable: Whether the type is an Assignable (a work item)
        is_global: Whether the type is global rather than project-scoped
        is_team_assignable: Whether team context applies to the type
        hierarchy_level: Sort rank on views with an entity-type axis
        has_audit_history: Whether the type keeps an audit history
        is_extendable: Whether the type can carry custom fields
    """

    custom_field_scope: str | None = Field(
        default=None, alias="CustomFieldScope", description="Custom-field scope"
    )
    is_searchable: bool | None = Field(default=None, alias="IsSearchable", description="Searchable")
    is_unit_in_hour_only: bool | None = Field(
        default=None, alias="IsUnitInHourOnly", description="Effort is hours-only"
    )
    is_assignable: bool | None = Field(
        default=None, alias="IsAssignable", description="Is a work item type"
    )
    is_global: bool | None = Field(default=None, alias="IsGlobal", description="Global type")
    is_team_assignable: bool | None = Field(
        default=None, alias="IsTeamAssignable", description="Team context applies"
    )
    hierarchy_level: int | None = Field(
        default=None, alias="HierarchyLevel", description="Sort rank on entity-type axes"
    )
    has_audit_history: bool | None = Field(
        default=None, alias="HasAuditHistory", description="Keeps an audit history"
    )
    is_extendable: bool | None = Field(
        default=None, alias="IsExtendable", description="Can carry custom fields"
    )


class Term(Entity):
    """Term entity - a process's vocabulary override for an entity type.

    A Term maps a ``word_key`` (the built-in word) to the ``value`` one
    process displays instead, so an instance can call a User Story a
    "Ticket" in one process and not another. It carries no ``Name``, so it
    extends :class:`targetprocess._base.Entity` directly. TP declares the
    collection read-only and marks it beta.

    Attributes:
        word_key: The built-in word being overridden
        value: The display value the process uses
        process: Owning process reference
        entity_type: Entity type the term applies to
    """

    word_key: str | None = Field(default=None, alias="WordKey", description="Built-in word")
    value: str | None = Field(default=None, alias="Value", description="Display value")
    process: EntityRef | None = Field(default=None, alias="Process", description="Process")
    entity_type: EntityTypeRef | None = Field(
        default=None, alias="EntityType", description="Entity type"
    )


class CustomActivity(NamedEntity):
    """CustomActivity entity - a project-scoped activity that Time is logged against.

    The non-work-item target for time tracking: a ``Time`` record may
    reference one of these instead of an ``Assignable`` (see
    ``Time.custom_activity``). Activities are scoped to a ``Project`` and a
    ``User``, so a name may repeat across projects.

    Attributes:
        created: When the activity was created
        estimate: Estimated effort for the activity
        project: Owning project reference
        user: User the activity belongs to
    """

    created: TPDateTime | None = Field(
        default=None, alias="Created", description="Creation timestamp"
    )
    estimate: float | None = Field(default=None, alias="Estimate", description="Estimated effort")
    project: EntityRef | None = Field(default=None, alias="Project", description="Project")
    user: UserRef | None = Field(default=None, alias="User", description="Owning user")


class CustomRule(NamedEntity):
    """CustomRule entity - a user-defined business rule on the instance.

    TP exposes rules for inspection and toggling only: the collection's
    ``/meta`` declares it neither creatable nor deletable, and ``is_enabled``
    is the one settable field, so ``client.custom_rules`` accepts ``update``
    and refuses ``create`` and ``delete`` in every mode.

    Attributes:
        description: Brief description of the rule
        is_enabled: Whether the rule is switched on (the only settable field)
    """

    description: str | None = Field(
        default=None, alias="Description", description="Rule description"
    )
    is_enabled: bool | None = Field(default=None, alias="IsEnabled", description="Switched on")
