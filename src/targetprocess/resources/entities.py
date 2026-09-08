"""Generic entity resource manager."""

import builtins
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any

from targetprocess._entity_types import require_entity_type
from targetprocess.models import NamedEntity
from targetprocess.resources.base import (
    BaseResource,
    WriteOperation,
    _require_ids,
    _require_no_ids,
    _with_canonical_id,
)
from targetprocess.resources.custom_rules import CustomRulesResource
from targetprocess.resources.entity_types import EntityTypesResource
from targetprocess.resources.processes import ProcessesResource
from targetprocess.resources.relation_types import RelationTypesResource
from targetprocess.resources.terms import TermsResource
from targetprocess.response_parser import ResponseParser

if TYPE_CHECKING:
    from targetprocess.client import TargetProcessClient
    from targetprocess.request_handler import RequestHandler


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


class EntitiesResource:
    """Generic resource for any entity type known only at runtime.

    Unlike typed resources (UserStoriesResource, etc.), this works with any
    entity type at runtime: every method takes the entity type name as its
    first positional argument. It is the full read *and* write surface for
    the collections with no typed manager - writes are gated by the same
    ``ClientMode.READWRITE`` check as the typed resources, and an operation
    TP itself declares a collection incapable of is refused in every mode,
    exactly as its typed resource refuses it (see ``_check_server_writable``).

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
                ``skip`` is negative, ``innertake`` is negative, or
                ``include`` names a field the typed resource for this
                collection refuses to hydrate (raised when iteration begins)
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: API errors
        """
        _check_include(entity_type, include)
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

    async def create(self, entity_type: str, /, **fields: Any) -> NamedEntity:
        """Create a new entity of any type.

        Requires client mode to be READWRITE.

        Args:
            entity_type: TP entity type name (e.g., "Objective")
            **fields: Entity field values, in the API's wire shape
                (e.g. ``Name="Q3 goal", Project={"Id": 2}``)

        Returns:
            The created entity, as a NamedEntity

        Raises:
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
        data = await self._request_handler.create(entity_type, fields)
        return ResponseParser.parse_single(data, NamedEntity)

    async def update(self, entity_type: str, id: int, /, **fields: Any) -> NamedEntity:
        """Update an existing entity of any type.

        Requires client mode to be READWRITE.

        Args:
            entity_type: TP entity type name (e.g., "Objective")
            id: Entity ID
            **fields: Entity field values to update, in the API's wire shape

        Returns:
            The updated entity, as a NamedEntity

        Raises:
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
        self, entity_type: str, items: Sequence[dict[str, Any]]
    ) -> builtins.list[NamedEntity]:
        """Create several entities of any type in one bulk request.

        The generic counterpart of ``BaseResource.create_many`` - same
        gates, same ``Id``-less item validation, same single
        ``POST /{collection}/bulk`` request; see that method (and SPEC.md's
        "Bulk write semantics") for the endpoint's semantics.

        Args:
            entity_type: TP entity type name (e.g., "Objective")
            items: Field dicts, one per entity to create

        Returns:
            The created entities, as NamedEntity instances

        Raises:
            ValueError: An item carries an ``Id`` key.
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
        data = await self._request_handler.bulk(entity_type, items)
        return [ResponseParser.parse_single(item, NamedEntity) for item in data]

    async def update_many(
        self, entity_type: str, items: Sequence[dict[str, Any]]
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

        Returns:
            The updated entities, as NamedEntity instances

        Raises:
            ValueError: An item has no ``Id`` key.
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
        data = await self._request_handler.bulk(entity_type, items)
        return [ResponseParser.parse_single(item, NamedEntity) for item in data]
