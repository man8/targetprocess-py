"""Generic entity resource manager."""

import builtins
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any

from targetprocess_py._entity_types import require_entity_type
from targetprocess_py.models import NamedEntity
from targetprocess_py.resources._derived import (
    ASSIGNABLE_DERIVED_FIELDS,
    check_derived_fields,
    check_derived_items,
)
from targetprocess_py.resources.base import (
    ASSIGNABLE_IGNORED_FILTER_PATHS,
    BaseResource,
    WriteOperation,
    _require_ids,
    _require_no_ids,
    _with_canonical_id,
    check_filter_paths,
)
from targetprocess_py.resources.bugs import BugsResource
from targetprocess_py.resources.custom_rules import CustomRulesResource
from targetprocess_py.resources.entity_types import EntityTypesResource
from targetprocess_py.resources.epics import EpicsResource
from targetprocess_py.resources.features import FeaturesResource
from targetprocess_py.resources.processes import ProcessesResource
from targetprocess_py.resources.relation_types import RelationTypesResource
from targetprocess_py.resources.requests import RequestsResource
from targetprocess_py.resources.tasks import TasksResource
from targetprocess_py.resources.terms import TermsResource
from targetprocess_py.resources.user_stories import UserStoriesResource
from targetprocess_py.response_parser import ResponseParser

if TYPE_CHECKING:
    from targetprocess_py.client import TargetProcessClient
    from targetprocess_py.request_handler import RequestHandler


def _spellings(entity_type: str) -> frozenset[str]:
    """Every spelling TP accepts for one collection, casefolded.

    TP addresses a collection by its singular entity type or its plural
    (``Process`` / ``Processes``, ``Severity`` / ``Severities``), so a guard
    keyed on the typed resource's ``entity_type`` must answer to both. The
    plural is derived, not folded off the caller's spelling: stripping a
    trailing ``s`` would turn ``Processes`` into ``processe`` and the
    singular ``Process`` into ``proces``, and the two would never meet.
    """
    singular = entity_type.casefold()
    plurals = {singular + "s", singular + "es"}
    if singular.endswith("y"):
        plurals.add(singular[:-1] + "ies")
    return frozenset({singular, *plurals})


def _by_spelling(*classes: type[BaseResource[Any]]) -> dict[str, type[BaseResource[Any]]]:
    """Map every accepted spelling of each class's collection to the class."""
    return {
        spelling: resource for resource in classes for spelling in _spellings(resource.entity_type)
    }


# Every typed resource whose collection TP restricts on the server side,
# keyed by each spelling the caller may use. A typed resource carries the
# restriction as its ``server_read_only`` / ``server_can_*`` class flags; the
# generic resource takes its entity type at runtime, so the same classes are
# consulted here by name, and the per-operation answer is the class's own
# ``server_permits``. ``tests/test_resources/test_entities.py`` walks every
# exported resource and fails if one with a restriction is missing from this
# map, or if its collection's singular or plural spelling does not reach it.
_SERVER_GUARDED_RESOURCES: dict[str, type[BaseResource[Any]]] = _by_spelling(
    RelationTypesResource,
    EntityTypesResource,
    TermsResource,
    CustomRulesResource,
)


# The read-side counterpart: every typed resource that refuses an include=
# its collection cannot hydrate (``BaseResource.unhydratable_includes``),
# keyed the same way so the generic path refuses it too, before any request,
# rather than failing the parse afterwards. The walk test in
# ``tests/test_resources/test_entities.py`` covers this map as well.
_UNHYDRATABLE_RESOURCES: dict[str, type[BaseResource[Any]]] = _by_spelling(ProcessesResource)


def _check_include(entity_type: str, include: list[str] | None) -> None:
    """Apply the typed resource's include refusal to a generic read, if one exists."""
    guarded = _UNHYDRATABLE_RESOURCES.get(entity_type.casefold())
    if guarded is not None:
        guarded.check_include(include)


# Assignable-derived collections with no typed manager, so reachable only
# through this accessor - which makes keying them here the only place the
# refusal can be applied. Each one's ``/meta`` declares an ``Assignments``
# collection alongside the rest of the assignable surface (``AssignedUser``,
# ``Times``, ``RoleEfforts``, ``Impediments``, ``TeamStates``). Named in the
# singular; ``_spellings`` derives the plural TP addresses the collection by.
#
# ``PortfolioEpic``, ``TestPlanRun``, ``InboundAssignable`` and
# ``OutboundAssignable`` were each confirmed live, against an unfiltered control
# on the same collection. The polymorphic ``Assignable`` is carried on the
# narrower argument that it returns a superset of the same rows as the six typed
# collections, so it cannot behave differently from them.
#
# This is what has been checked, not every candidate: the collections were named
# for checking rather than enumerated from the instance, so an untyped
# Assignable-derived collection missing here is unproven, not cleared. The
# TestPlan family is the obvious one left - ``TestPlanRun`` is covered and
# ``TestPlan`` is not. Add one the same way, with its own unfiltered control.
#
# ``Inbound``/``OutboundAssignables`` are also read as ``include=`` collection
# properties of an item, which is unaffected: the refusal is on ``list()``'s
# ``where=`` only.
_UNTYPED_ASSIGNABLE_COLLECTIONS: tuple[str, ...] = (
    "Assignable",
    "PortfolioEpic",
    "TestPlanRun",
    "InboundAssignable",
    "OutboundAssignable",
)


# The where= counterpart: the ignored-filter declaration of every assignable
# collection (``BaseResource.ignored_filter_paths``), keyed by each spelling the
# caller may use, so the generic path refuses the same filters before any
# request rather than returning the unfiltered rows TP answers with. Keyed
# spelling -> reasons rather than spelling -> class, because the collections in
# ``_UNTYPED_ASSIGNABLE_COLLECTIONS`` have no typed manager to consult and are
# the same server behaviour on the same rows. The walk test in
# ``tests/test_resources/test_ignored_filter_paths.py`` covers this map.
_IGNORED_FILTER_PATHS: dict[str, dict[str, str]] = {
    spelling: resource.ignored_filter_paths
    for resource in (
        UserStoriesResource,
        BugsResource,
        TasksResource,
        FeaturesResource,
        EpicsResource,
        RequestsResource,
    )
    for spelling in _spellings(resource.entity_type)
} | {
    spelling: ASSIGNABLE_IGNORED_FILTER_PATHS
    for collection in _UNTYPED_ASSIGNABLE_COLLECTIONS
    for spelling in _spellings(collection)
}


def _check_where(entity_type: str, where: str | None) -> None:
    """Apply the ignored-filter refusal to a generic list, reporting the caller's spelling."""
    check_filter_paths(
        where, _IGNORED_FILTER_PATHS.get(entity_type.casefold(), {}), resource=entity_type
    )


# The write-side counterpart, keyed and populated exactly as
# ``_IGNORED_FILTER_PATHS`` is: the derived-field declaration of every
# assignable collection, so the generic path refuses the same write before any
# request rather than letting TP answer a success status that means nothing.
# Without this the generic accessor would be the way round the typed guard,
# which is the one thing it must not be. The walk test in
# ``tests/test_resources/test_role_efforts.py`` covers this map.
_DERIVED_FIELDS: dict[str, dict[str, str]] = {
    spelling: resource.derived_fields
    for resource in (
        UserStoriesResource,
        BugsResource,
        TasksResource,
        FeaturesResource,
        EpicsResource,
        RequestsResource,
    )
    for spelling in _spellings(resource.entity_type)
} | {
    spelling: ASSIGNABLE_DERIVED_FIELDS
    for collection in _UNTYPED_ASSIGNABLE_COLLECTIONS
    for spelling in _spellings(collection)
}


def _derived_for(entity_type: str) -> dict[str, str]:
    """Return the derived-field declaration for a collection, empty when it has none."""
    return _DERIVED_FIELDS.get(entity_type.casefold(), {})


class EntitiesResource:
    """Generic resource for any entity type known only at runtime.

    Unlike typed resources (UserStoriesResource, etc.), this works with any
    entity type at runtime: every method takes the entity type name as its
    first positional argument. It is the full read *and* write surface for
    the collections with no typed manager - writes are gated by the same
    ``ClientMode.READWRITE`` check as the typed resources, and an operation
    TP itself declares a collection incapable of is refused in every mode,
    exactly as its typed resource refuses it (see ``_check_server_writable``).
    A write naming a field TP derives from another collection is refused here
    too, for every spelling of the assignable collections, so the generic
    accessor is not a way round the typed guard; ``allow_derived=True`` sends
    it anyway.

    Reads parse into :class:`NamedEntity` rather than bare :class:`Entity`,
    so named types (Bug, UserStory, ...) keep their ``.name``. Payloads with
    no Name key (e.g. Users) parse fine too - ``name`` is optional and comes
    back ``None``.

    Example:
        client = TargetProcessClient(...)
        bug = await client.entities.get("Bug", 123)
        async for story in client.entities.list("UserStory", limit=10):
            print(story.name)
        objective = await client.entities.create(
            "Objective", Name="Q3 goal", Project={"Id": 2}
        )
    """

    def __init__(
        self,
        client: "TargetProcessClient",
        request_handler: "RequestHandler",
    ) -> None:
        """Initialize generic entities resource.

        Args:
            client: TargetProcessClient instance
            request_handler: RequestHandler for API operations
        """
        self._client = client
        self._request_handler = request_handler

    @staticmethod
    def _check_server_writable(entity_type: str, operation: WriteOperation) -> None:
        """Refuse a write TP declares the collection incapable of.

        Mirrors ``BaseResource._check_server_writable``: the typed resource
        for such a collection carries ``server_read_only`` or a
        ``server_can_*`` flag on its class, and the generic path applies the
        same per-operation refusal by entity-type name (any casing, singular
        or plural). The name is shape-checked first, so a perturbed spelling
        (``"RelationTypes/"``, a leading space, an embedded path segment) is
        refused as malformed rather than slipping past the name lookup - the
        generic path cannot be used to sidestep the typed guard.

        Args:
            entity_type: The entity type name the caller supplied
            operation: The attempted operation (create, update, delete)

        Raises:
            ValueError: ``entity_type`` is not a plain TP identifier.
            ReadOnlyViolation: The collection is read-only on the server, or
                does not accept this operation (raised in every client mode,
                before any request is sent).
        """
        require_entity_type(entity_type)
        guarded = _SERVER_GUARDED_RESOURCES.get(entity_type.casefold())
        if guarded is not None and not guarded.server_permits(operation):
            # Deliberately the typed class's own private builder, shared
            # across the resources package the way ``_require_ids`` is: the
            # refusal must read identically on both paths, and the builder
            # is not part of the public surface a caller composes with.
            raise guarded._server_refusal(operation, entity_type)

    async def get(
        self,
        entity_type: str,
        id: int,
        *,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        result_include: list[str] | None = None,
        append: list[str] | None = None,
        innertake: int | None = None,
    ) -> NamedEntity:
        """Fetch single entity by type and ID.

        Args:
            entity_type: TP entity type name (e.g., "UserStory", "Bug")
            id: Entity ID
            include: Optional list of fields to include
            exclude: Optional list of fields to exclude from the response
                (server-side; the complement of ``include``)
            result_include: Optional list of fields to restrict the response
                to - server-side payload narrowing (``resultInclude=``)
            append: Optional list of calculated fields to append
                (e.g. ``["Tasks-Count"]``)
            innertake: Optional bound on the size of nested collections
                hydrated via ``include``

        Returns:
            NamedEntity instance

        Raises:
            ValueError: ``innertake`` is negative, or ``include`` names a
                field the typed resource for this collection refuses to
                hydrate
            NotFoundError: Entity not found
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        _check_include(entity_type, include)
        data = await self._request_handler.get(
            entity_type,
            id,
            include=include,
            exclude=exclude,
            result_include=result_include,
            append=append,
            innertake=innertake,
        )
        return ResponseParser.parse_single(data, NamedEntity)

    async def list(
        self,
        entity_type: str,
        *,
        where: str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        result_include: list[str] | None = None,
        append: list[str] | None = None,
        innertake: int | None = None,
        order_by: str | None = None,
        order_by_desc: str | None = None,
        skip: int | None = None,
        limit: int | None = None,
        page_size: int = 25,
    ) -> AsyncIterator[NamedEntity]:
        """List entities by type with optional filtering, sorting, and shaping.

        Args:
            entity_type: TP entity type name (e.g., "UserStory", "Bug")
            where: TP `where=` filter expression (e.g.
                ``"(EntityState.IsFinal eq 'false')"``)
            include: Optional list of fields to include
            exclude: Optional list of fields to exclude from the response
                (server-side; the complement of ``include``)
            result_include: Optional list of fields to restrict each item
                to - server-side payload narrowing (``resultInclude=``)
            append: Optional list of calculated fields to append
                (e.g. ``["Tasks-Count"]``)
            innertake: Optional bound on the size of nested collections
                hydrated via ``include``
            order_by: Optional field to sort by, ascending, server-side;
                mutually exclusive with ``order_by_desc``
            order_by_desc: Optional field to sort by, descending,
                server-side; mutually exclusive with ``order_by``
            skip: Optional server-side offset before the first yielded item.
                Opt-in: the default is the forward-only ``Next`` walk from
                offset 0; pagination follows ``Next`` verbatim either way.
            limit: Maximum TOTAL number of entities to yield (None = unbounded)
            page_size: Page size for each underlying request

        Yields:
            NamedEntity instances

        Raises:
            ValueError: Both ``order_by`` and ``order_by_desc`` were passed,
                ``skip`` is negative, ``innertake`` is negative,
                ``include`` names a field the typed resource for this
                collection refuses to hydrate, or ``where`` names a path TP
                will not filter on for an assignable collection (raised when
                iteration begins)
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: API errors
        """
        _check_include(entity_type, include)
        _check_where(entity_type, where)
        async for item_data in self._request_handler.list(
            entity_type,
            where=where,
            include=include,
            exclude=exclude,
            result_include=result_include,
            append=append,
            innertake=innertake,
            order_by=order_by,
            order_by_desc=order_by_desc,
            skip=skip,
            limit=limit,
            page_size=page_size,
        ):
            yield ResponseParser.parse_single(item_data, NamedEntity)

    async def create(
        self, entity_type: str, /, *, allow_derived: bool = False, **fields: Any
    ) -> NamedEntity:
        """Create a new entity of any type.

        Requires client mode to be READWRITE.

        Args:
            entity_type: TP entity type name (e.g., "Objective")
            allow_derived: Send a field the collection declares derived
                instead of refusing it (default False)
            **fields: Entity field values, in the API's wire shape
                (e.g. ``Name="Q3 goal", Project={"Id": 2}``)

        Returns:
            The created entity, as a NamedEntity

        Raises:
            ValueError: ``entity_type`` is not a plain TP identifier, or a
                field is one TP derives for that collection and
                ``allow_derived`` is False (raised before the request)
            ReadOnlyViolation: Client is in readonly mode, or the collection
                is read-only on the server (any mode)
            RequestValidationError: Invalid field values
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        self._check_server_writable(entity_type, "create")
        self._client._check_write_permission()
        if not allow_derived:
            check_derived_fields(fields, _derived_for(entity_type), resource=entity_type)
        data = await self._request_handler.create(entity_type, fields)
        return ResponseParser.parse_single(data, NamedEntity)

    async def update(
        self, entity_type: str, id: int, /, *, allow_derived: bool = False, **fields: Any
    ) -> NamedEntity:
        """Update an existing entity of any type.

        Requires client mode to be READWRITE.

        Args:
            entity_type: TP entity type name (e.g., "Objective")
            id: Entity ID
            allow_derived: Send a field the collection declares derived
                instead of refusing it (default False)
            **fields: Entity field values to update, in the API's wire shape

        Returns:
            The updated entity, as a NamedEntity

        Raises:
            ValueError: ``entity_type`` is not a plain TP identifier, or a
                field is one TP derives for that collection and
                ``allow_derived`` is False (raised before the request)
            ReadOnlyViolation: Client is in readonly mode, or the collection
                is read-only on the server (any mode)
            NotFoundError: Entity not found
            RequestValidationError: Invalid field values
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        self._check_server_writable(entity_type, "update")
        self._client._check_write_permission()
        if not allow_derived:
            check_derived_fields(fields, _derived_for(entity_type), resource=entity_type)
        data = await self._request_handler.update(entity_type, id, fields)
        return ResponseParser.parse_single(data, NamedEntity)

    async def delete(self, entity_type: str, id: int) -> None:
        """Delete an entity of any type.

        Requires client mode to be READWRITE.

        Args:
            entity_type: TP entity type name (e.g., "Objective")
            id: Entity ID

        Raises:
            ReadOnlyViolation: Client is in readonly mode, or the collection
                is read-only on the server (any mode)
            NotFoundError: Entity not found
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            APIError: Other API errors
        """
        self._check_server_writable(entity_type, "delete")
        self._client._check_write_permission()
        await self._request_handler.delete(entity_type, id)

    # Return annotations on methods defined after ``list`` above must spell
    # ``builtins.list``: in class scope the method name shadows the builtin.
    async def create_many(
        self,
        entity_type: str,
        items: Sequence[dict[str, Any]],
        *,
        allow_derived: bool = False,
    ) -> builtins.list[NamedEntity]:
        """Create several entities of any type in one bulk request.

        The generic counterpart of ``BaseResource.create_many`` - same
        gates, same ``Id``-less item validation, same single
        ``POST /{collection}/bulk`` request; see that method (and SPEC.md's
        "Bulk write semantics") for the endpoint's semantics.

        Args:
            entity_type: TP entity type name (e.g., "Objective")
            items: Field dicts, one per entity to create
            allow_derived: Send a field the collection declares derived
                instead of refusing it (default False)

        Returns:
            The created entities, as NamedEntity instances

        Raises:
            ValueError: An item carries an ``Id`` key, or names a field TP
                derives for that collection while ``allow_derived`` is False.
            ReadOnlyViolation: Client is in readonly mode, or the collection
                is read-only on the server (any mode)
            RequestValidationError: Invalid field values
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation, or the bulk
                response body had an unrecognised shape
            APIError: Other API errors
        """
        self._check_server_writable(entity_type, "create")
        self._client._check_write_permission()
        items = list(items)  # materialise once: validated and sent as the same batch
        _require_no_ids(items)
        if not allow_derived:
            check_derived_items(
                items, _derived_for(entity_type), resource=entity_type, operation="create_many"
            )
        data = await self._request_handler.bulk(entity_type, items)
        return [ResponseParser.parse_single(item, NamedEntity) for item in data]

    async def update_many(
        self,
        entity_type: str,
        items: Sequence[dict[str, Any]],
        *,
        allow_derived: bool = False,
    ) -> builtins.list[NamedEntity]:
        """Update several entities of any type in one bulk request.

        The generic counterpart of ``BaseResource.update_many`` - same
        gates, same ``Id``-bearing item validation, same single
        ``POST /{collection}/bulk`` request; see that method (and SPEC.md's
        "Bulk write semantics") for the endpoint's semantics.

        Args:
            entity_type: TP entity type name (e.g., "Objective")
            items: Field dicts, one per entity to update, each carrying the
                target's ``Id``
            allow_derived: Send a field the collection declares derived
                instead of refusing it (default False)

        Returns:
            The updated entities, as NamedEntity instances

        Raises:
            ValueError: An item has no ``Id`` key, or names a field TP derives
                for that collection while ``allow_derived`` is False.
            ReadOnlyViolation: Client is in readonly mode, or the collection
                is read-only on the server (any mode)
            NotFoundError: A referenced entity was not found
            RequestValidationError: Invalid field values
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation, or the bulk
                response body had an unrecognised shape
            APIError: Other API errors
        """
        self._check_server_writable(entity_type, "update")
        self._client._check_write_permission()
        items = list(items)  # materialise once: validated and sent as the same batch
        _require_ids(items)
        items = [_with_canonical_id(item) for item in items]
        if not allow_derived:
            check_derived_items(
                items, _derived_for(entity_type), resource=entity_type, operation="update_many"
            )
        data = await self._request_handler.bulk(entity_type, items)
        return [ResponseParser.parse_single(item, NamedEntity) for item in data]
