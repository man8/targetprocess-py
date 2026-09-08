"""Main client for TargetProcess API."""

from typing import Any

import httpx

from targetprocess.exceptions import ReadOnlyViolation
from targetprocess.request_handler import RequestHandler
from targetprocess.resources import (
    AssignmentsResource,
    AttachmentsResource,
    BugsResource,
    CommentsResource,
    CustomActivitiesResource,
    CustomFieldsResource,
    CustomRulesResource,
    EntitiesResource,
    EntityStatesResource,
    EntityTypesResource,
    EpicsResource,
    FeaturesResource,
    IterationsResource,
    PrioritiesResource,
    ProcessesResource,
    ProjectsResource,
    RelationsResource,
    RelationTypesResource,
    ReleasesResource,
    RequestsResource,
    RoleEffortsResource,
    RolesResource,
    SeveritiesResource,
    TasksResource,
    TeamAssignmentsResource,
    TeamIterationsResource,
    TeamsResource,
    TermsResource,
    TestCasesResource,
    TimesResource,
    UsersResource,
    UserStoriesResource,
    WorkflowsResource,
)
from targetprocess.transport import HTTPTransport
from targetprocess.types import ClientMode


class TargetProcessClient:
    """Async client for TargetProcess API.

    Args:
        domain: TargetProcess domain (e.g., "example.tpondemand.com")
        mode: Client operation mode (READONLY or READWRITE) — keyword-only,
            required, with no default, so every client is constructed with
            an explicit safety posture.
        token: API authentication token, sent as the `access_token` query
            parameter — TP's documented token scheme (there is no header-borne
            token scheme). Because the token is carried in the request URL, it
            will appear in URLs and server logs — do not enable httpx
            request-URL logging in production. Mutually exclusive with
            `basic_auth`.
        basic_auth: (username, password) tuple, sent as an `Authorization:
            Basic` header — the header-based alternative to `token`. Mutually
            exclusive with `token`.
        timeout: Request timeout in seconds (default: 30)

    Example:
        async with TargetProcessClient(
            domain="example.tpondemand.com",
            token="your-token",
            mode=ClientMode.READONLY,
        ) as client:
            # Use client for API calls
            pass
    """

    def __init__(
        self,
        domain: str,
        *,
        mode: ClientMode,
        token: str | None = None,
        basic_auth: tuple[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the TargetProcess client.

        Args:
            domain: TargetProcess domain (e.g., "example.tpondemand.com")
            mode: Client operation mode (READONLY or READWRITE)
            token: API authentication token, sent as the `access_token` query
                parameter. Mutually exclusive with `basic_auth`.
            basic_auth: (username, password) tuple, sent as an `Authorization:
                Basic` header. Mutually exclusive with `token`.
            timeout: Request timeout in seconds (default: 30)
        """
        # Store domain without https:// prefix
        self._domain = domain.replace("https://", "").replace("http://", "")
        # Coerce/validate: raises ValueError for any value that isn't a
        # recognized ClientMode, so an unrecognized mode fails closed instead
        # of silently falling through to readwrite-permissive behavior.
        self._mode = ClientMode(mode)
        self._mode_frozen = False

        # Create timeout configuration
        timeout_config = httpx.Timeout(timeout, connect=5.0, read=timeout)

        # Initialize HTTP transport
        self._transport = HTTPTransport(
            domain=self._domain,
            token=token,
            basic_auth=basic_auth,
            timeout=timeout_config,
        )

        # Initialize request handler - inject the write-permission check so
        # writes are refused at the handler layer too (defense in depth),
        # not just at the resource layer.
        self._request_handler = RequestHandler(
            self._transport, check_write=self._check_write_permission
        )

        # Freeze mode after initialization
        self._mode_frozen = True

    @property
    def domain(self) -> str:
        """Get the TargetProcess domain."""
        return self._domain

    @property
    def mode(self) -> ClientMode:
        """Get the client operation mode."""
        return self._mode

    def __setattr__(self, name: str, value: Any) -> None:
        """Override setattr to prevent mode changes after initialization.

        Guards three names: the public ``mode`` property is always
        read-only, and ``_mode`` / ``_mode_frozen`` both become immutable
        once the freeze flag is set - so the guard flag itself can't be
        unset to reopen the mode for writing (best-effort against ordinary
        attribute assignment, not a hard sandbox).

        Args:
            name: Attribute name
            value: Attribute value

        Raises:
            AttributeError: If attempting to change mode (or the freeze
                flag protecting it) after initialization
        """
        if name == "mode":
            raise AttributeError("mode is immutable and cannot be changed after initialization")

        # Once frozen, neither the mode itself nor the flag that freezes it
        # can be reassigned.
        if name in ("_mode", "_mode_frozen") and getattr(self, "_mode_frozen", False):
            raise AttributeError("mode is immutable and cannot be changed after initialization")

        super().__setattr__(name, value)

    def _check_write_permission(self) -> None:
        """Check if write operations are allowed.

        Raises:
            ReadOnlyViolation: If client is in READONLY mode
        """
        if self._mode == ClientMode.READONLY:
            raise ReadOnlyViolation()

    # Resource properties - lazily initialized

    @property
    def user_stories(self) -> UserStoriesResource:
        """Access UserStory resources."""
        if not hasattr(self, "_user_stories"):
            self._user_stories = UserStoriesResource(self, self._request_handler)
        return self._user_stories

    @property
    def bugs(self) -> BugsResource:
        """Access Bug resources."""
        if not hasattr(self, "_bugs"):
            self._bugs = BugsResource(self, self._request_handler)
        return self._bugs

    @property
    def tasks(self) -> TasksResource:
        """Access Task resources."""
        if not hasattr(self, "_tasks"):
            self._tasks = TasksResource(self, self._request_handler)
        return self._tasks

    @property
    def features(self) -> FeaturesResource:
        """Access Feature resources."""
        if not hasattr(self, "_features"):
            self._features = FeaturesResource(self, self._request_handler)
        return self._features

    @property
    def epics(self) -> EpicsResource:
        """Access Epic resources."""
        if not hasattr(self, "_epics"):
            self._epics = EpicsResource(self, self._request_handler)
        return self._epics

    @property
    def requests(self) -> RequestsResource:
        """Access Request resources."""
        if not hasattr(self, "_requests"):
            self._requests = RequestsResource(self, self._request_handler)
        return self._requests

    @property
    def test_cases(self) -> TestCasesResource:
        """Access TestCase resources."""
        if not hasattr(self, "_test_cases"):
            self._test_cases = TestCasesResource(self, self._request_handler)
        return self._test_cases

    @property
    def times(self) -> TimesResource:
        """Access Time resources."""
        if not hasattr(self, "_times"):
            self._times = TimesResource(self, self._request_handler)
        return self._times

    @property
    def releases(self) -> ReleasesResource:
        """Access Release resources."""
        if not hasattr(self, "_releases"):
            self._releases = ReleasesResource(self, self._request_handler)
        return self._releases

    @property
    def iterations(self) -> IterationsResource:
        """Access Iteration resources."""
        if not hasattr(self, "_iterations"):
            self._iterations = IterationsResource(self, self._request_handler)
        return self._iterations

    @property
    def projects(self) -> ProjectsResource:
        """Access Project resources."""
        if not hasattr(self, "_projects"):
            self._projects = ProjectsResource(self, self._request_handler)
        return self._projects

    @property
    def teams(self) -> TeamsResource:
        """Access Team resources."""
        if not hasattr(self, "_teams"):
            self._teams = TeamsResource(self, self._request_handler)
        return self._teams

    @property
    def users(self) -> UsersResource:
        """Access User resources."""
        if not hasattr(self, "_users"):
            self._users = UsersResource(self, self._request_handler)
        return self._users

    @property
    def entity_states(self) -> EntityStatesResource:
        """Access EntityState resources."""
        if not hasattr(self, "_entity_states"):
            self._entity_states = EntityStatesResource(self, self._request_handler)
        return self._entity_states

    @property
    def priorities(self) -> PrioritiesResource:
        """Access Priority resources."""
        if not hasattr(self, "_priorities"):
            self._priorities = PrioritiesResource(self, self._request_handler)
        return self._priorities

    @property
    def comments(self) -> CommentsResource:
        """Access Comment resources."""
        if not hasattr(self, "_comments"):
            self._comments = CommentsResource(self, self._request_handler)
        return self._comments

    @property
    def assignments(self) -> AssignmentsResource:
        """Access Assignment resources."""
        if not hasattr(self, "_assignments"):
            self._assignments = AssignmentsResource(self, self._request_handler)
        return self._assignments

    @property
    def team_assignments(self) -> TeamAssignmentsResource:
        """Access TeamAssignment resources."""
        if not hasattr(self, "_team_assignments"):
            self._team_assignments = TeamAssignmentsResource(self, self._request_handler)
        return self._team_assignments

    @property
    def role_efforts(self) -> RoleEffortsResource:
        """Access RoleEffort resources."""
        if not hasattr(self, "_role_efforts"):
            self._role_efforts = RoleEffortsResource(self, self._request_handler)
        return self._role_efforts

    @property
    def roles(self) -> RolesResource:
        """Access Role resources."""
        if not hasattr(self, "_roles"):
            self._roles = RolesResource(self, self._request_handler)
        return self._roles

    @property
    def attachments(self) -> AttachmentsResource:
        """Access Attachment resources."""
        if not hasattr(self, "_attachments"):
            self._attachments = AttachmentsResource(self, self._request_handler)
        return self._attachments

    @property
    def relations(self) -> RelationsResource:
        """Access Relation resources."""
        if not hasattr(self, "_relations"):
            self._relations = RelationsResource(self, self._request_handler)
        return self._relations

    @property
    def relation_types(self) -> RelationTypesResource:
        """Access RelationType resources."""
        if not hasattr(self, "_relation_types"):
            self._relation_types = RelationTypesResource(self, self._request_handler)
        return self._relation_types

    @property
    def team_iterations(self) -> TeamIterationsResource:
        """Access TeamIteration (team sprint) resources."""
        if not hasattr(self, "_team_iterations"):
            self._team_iterations = TeamIterationsResource(self, self._request_handler)
        return self._team_iterations

    @property
    def custom_fields(self) -> CustomFieldsResource:
        """Access CustomField definition resources."""
        if not hasattr(self, "_custom_fields"):
            self._custom_fields = CustomFieldsResource(self, self._request_handler)
        return self._custom_fields

    @property
    def severities(self) -> SeveritiesResource:
        """Access Severity resources."""
        if not hasattr(self, "_severities"):
            self._severities = SeveritiesResource(self, self._request_handler)
        return self._severities

    @property
    def processes(self) -> ProcessesResource:
        """Access Process resources."""
        if not hasattr(self, "_processes"):
            self._processes = ProcessesResource(self, self._request_handler)
        return self._processes

    @property
    def workflows(self) -> WorkflowsResource:
        """Access Workflow resources."""
        if not hasattr(self, "_workflows"):
            self._workflows = WorkflowsResource(self, self._request_handler)
        return self._workflows

    @property
    def entity_types(self) -> EntityTypesResource:
        """Access EntityType resources (server read-only)."""
        if not hasattr(self, "_entity_types"):
            self._entity_types = EntityTypesResource(self, self._request_handler)
        return self._entity_types

    @property
    def terms(self) -> TermsResource:
        """Access Term resources (server read-only)."""
        if not hasattr(self, "_terms"):
            self._terms = TermsResource(self, self._request_handler)
        return self._terms

    @property
    def custom_activities(self) -> CustomActivitiesResource:
        """Access CustomActivity resources."""
        if not hasattr(self, "_custom_activities"):
            self._custom_activities = CustomActivitiesResource(self, self._request_handler)
        return self._custom_activities

    @property
    def custom_rules(self) -> CustomRulesResource:
        """Access CustomRule resources (server update-only)."""
        if not hasattr(self, "_custom_rules"):
            self._custom_rules = CustomRulesResource(self, self._request_handler)
        return self._custom_rules

    @property
    def entities(self) -> EntitiesResource:
        """Access entities generically (any type at runtime)."""
        if not hasattr(self, "_entities"):
            self._entities = EntitiesResource(self, self._request_handler)
        return self._entities

    async def aclose(self) -> None:
        """Close the underlying HTTP client.

        Call this explicitly when the client isn't used as an async context
        manager, to avoid leaking the underlying ``httpx.AsyncClient``.
        """
        await self._transport.close()

    async def __aenter__(self) -> "TargetProcessClient":
        """Enter async context manager.

        Returns:
            Self for use in context
        """
        await self._transport.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised
        """
        await self.aclose()
