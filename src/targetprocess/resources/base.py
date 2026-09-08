"""Base resource class for all TargetProcess entity resources."""

import builtins
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any, Literal

from targetprocess.exceptions import AmbiguousMatchError, NotFoundError, ReadOnlyViolation
from targetprocess.models import Entity, NamedEntity
from targetprocess.response_parser import ResponseParser

if TYPE_CHECKING:
    from targetprocess.client import TargetProcessClient
    from targetprocess.request_handler import RequestHandler


# The three write operations a collection's /meta can permit or refuse
# (CanCreate / CanUpdate / CanDelete). The bulk methods map onto create and
# update; there is no bulk delete.
WriteOperation = Literal["create", "update", "delete"]


def _id_keys(item: dict[str, Any]) -> list[str]:
    """Return every key of ``item`` that spells ``Id``, in whatever casing.

    The wire field is ``Id``, but TP's JSON handling is not documented as
    case-sensitive, so a lowercase ``id`` is treated as the same field here -
    the guards below exist to catch exactly the mistakes a strict comparison
    would wave through. More than one match means the caller wrote the
    identifier twice and the update target is ambiguous.
    """
    return [key for key in item if key.casefold() == "id"]


def _id_key(item: dict[str, Any]) -> str | None:
    """Return the item's single ``Id`` key in whatever casing, or None."""
    keys = _id_keys(item)
    return keys[0] if keys else None


def _with_canonical_id(item: dict[str, Any]) -> dict[str, Any]:
    """Return ``item`` with its identifier under the wire key ``Id``.

    :func:`_id_key` accepts any casing so the shape guards catch mistakes, but
    the wire field is ``Id``: a lowercase ``id`` forwarded as-is could be read
    by TP as an ``Id``-less item - a create. Rewrite the key before dispatch;
    an item already keyed ``Id`` is returned unchanged.
    """
    key = _id_key(item)
    if key is None or key == "Id":
        return item
    return {"Id": item[key], **{k: v for k, v in item.items() if k != key}}


def _require_no_ids(items: Sequence[dict[str, Any]]) -> None:
    """Refuse a create-shaped bulk batch containing an ``Id``-bearing item.

    The bulk endpoint decides create-vs-update per item by the presence of
    an ``Id``, so an ``Id``-bearing item in a batch the caller named a
    *create* would silently update an existing entity instead.

    Raises:
        ValueError: An item carries an ``Id`` key (any casing).
    """
    for position, item in enumerate(items):
        key = _id_key(item)
        if key is not None:
            raise ValueError(
                f"create_many item {position} carries an {key!r} key "
                f"({item[key]!r}); on the bulk endpoint that updates the "
                "existing entity - use update_many for updates"
            )


def _require_ids(items: Sequence[dict[str, Any]]) -> None:
    """Refuse an update-shaped bulk batch containing an ``Id``-less item.

    The mirror of :func:`_require_no_ids`: an ``Id``-less item in a batch
    the caller named an *update* would silently create a new entity.

    Raises:
        ValueError: An item has no ``Id`` key (any casing), or carries the
            key under more than one casing.
    """
    for position, item in enumerate(items):
        keys = _id_keys(item)
        if not keys:
            raise ValueError(
                f"update_many item {position} has no 'Id' key; on the bulk "
                "endpoint an Id-less item creates a new entity - use "
                "create_many for creates"
            )
        if len(keys) > 1:
            raise ValueError(
                f"update_many item {position} carries more than one Id key "
                f"({', '.join(repr(k) for k in keys)}); the update target is "
                "ambiguous - keep exactly one, spelled 'Id'"
            )


def _resolve_by_name[N: NamedEntity](candidates: Sequence[N], name: str, *, what: str) -> N:
    """Return the single candidate whose ``Name`` equals ``name``, case-insensitively.

    The shared body of every ``resolve()``: a name matching zero or several
    candidates raises rather than picking one, so an ambiguous resolution
    never reaches the API.

    Args:
        candidates: The records to match against, already fetched
        name: Display name to resolve
        what: Noun for the messages (e.g. ``"role"``, ``"UserStory priority"``)

    Returns:
        The single matching candidate.

    Raises:
        NotFoundError: No candidate of that name exists (the message lists
            the names that do).
        AmbiguousMatchError: More than one candidate of that name matched.
    """
    wanted = name.casefold()
    matches = [c for c in candidates if (c.name or "").casefold() == wanted]
    if not matches:
        available = ", ".join(sorted(c.name for c in candidates if c.name)) or "none"
        raise NotFoundError(f"no {what} named {name!r}; available: {available}")
    if len(matches) > 1:
        ids = ", ".join(str(c.id) for c in matches)
        raise AmbiguousMatchError(f"{what} {name!r} matched {len(matches)} records (Ids: {ids})")
    return matches[0]


class BaseResource[T: Entity]:
    """Base class for all resource managers.

    Provides CRUD operations for TargetProcess entities with type safety.
    Subclasses must specify entity_type and model_class.

    Type Parameters:
        T: The entity model type (UserStory, Bug, Task, etc.)

    Attributes:
        entity_type: TP API entity type name (e.g., "UserStory")
        model_class: Pydantic model class for this entity type
        server_read_only: Whether TP declares the collection itself
            read-only - the shorthand for all three capability flags below
            being False. When True, create/update/delete raise
            ReadOnlyViolation in every client mode - READWRITE included -
            before any request is sent, since the server would refuse the
            write anyway.
        server_can_create: Whether the collection's ``/meta`` reports
            ``CanCreate``. False refuses ``create`` and ``create_many`` in
            every mode, before any request is sent.
        server_can_update: The ``CanUpdate`` counterpart, gating ``update``
            and ``update_many``.
        server_can_delete: The ``CanDelete`` counterpart, gating ``delete``.
        unhydratable_includes: Wire field names whose ``include=`` hydration
            TP serves in a shape the model cannot hold, each mapped to the
            reason and the route to use instead; ``get`` and ``list`` refuse
            them with ``ValueError`` before any request is sent.
    """

    entity_type: str  # Override in subclass
    model_class: type[T]  # Override in subclass
    # Wire field name -> why it cannot be hydrated on this collection (and the
    # route to use instead). get() and list() refuse an include= naming one
    # before any request is sent, because TP would answer with a shape the
    # model cannot parse. Empty on every collection but the ones that collide.
    unhydratable_includes: dict[str, str] = {}
    server_read_only: bool = False  # Override in server-side read-only subclasses
    # Per-operation server capability, from the collection's /meta. A
    # collection TP declares partially writable (CustomRules: update only)
    # overrides the one flag it lacks; server_read_only covers the all-false
    # case and takes precedence over these.
    server_can_create: bool = True
    server_can_update: bool = True
    server_can_delete: bool = True

    def __init__(
        self,
        client: "TargetProcessClient",
        request_handler: "RequestHandler",
    ) -> None:
        """Initialize resource manager.

        Args:
            client: TargetProcessClient instance for permission checks
            request_handler: RequestHandler for API operations
        """
        self._client = client
        self._request_handler = request_handler

    @classmethod
    def check_include(cls, include: list[str] | None) -> None:
        """Refuse an ``include`` naming a field this collection cannot hydrate.

        Matching is case-insensitive on the field's leading identifier, so a
        nested selection (``"CustomFields[Id]"``) is caught with the bare
        name. A collection with nothing in ``unhydratable_includes`` accepts
        every include, as before.

        Args:
            include: The ``include=`` field list a caller passed, if any

        Raises:
            ValueError: A field in ``include`` is one this collection cannot
                hydrate; the message says why and what to use instead.
        """
        if not include or not cls.unhydratable_includes:
            return
        reasons = {name.casefold(): reason for name, reason in cls.unhydratable_includes.items()}
        for field in include:
            reason = reasons.get(field.split("[", 1)[0].strip().casefold())
            if reason is not None:
                raise ValueError(
                    f"include={field!r} is not supported on {cls.entity_type}: {reason}"
                )

    @classmethod
    def server_permits(cls, operation: WriteOperation) -> bool:
        """Report whether TP accepts ``operation`` on this collection at all.

        Read from the class flags, so it answers for the collection rather
        than for a client: the client's own READONLY/READWRITE mode is a
        separate gate applied afterwards.

        Args:
            operation: The write to ask about (``create``, ``update`` or
                ``delete``; the bulk methods map onto the first two)

        Returns:
            False when the server would refuse the operation regardless of
            client mode; True otherwise.
        """
        if cls.server_read_only:
            return False
        permitted = {
            "create": cls.server_can_create,
            "update": cls.server_can_update,
            "delete": cls.server_can_delete,
        }
        return permitted[operation]

    @classmethod
    def _server_refusal(cls, operation: WriteOperation, resource: str) -> ReadOnlyViolation:
        """Build the ReadOnlyViolation for a server-refused ``operation``.

        Args:
            operation: The attempted operation (create, update, delete)
            resource: The entity type name to report - the class's own for
                a typed resource, the caller's spelling on the generic path

        Returns:
            The exception to raise, naming the server-side reason.
        """
        reason = (
            "the collection is read-only on the server"
            if cls.server_read_only
            else f"the collection does not accept {operation} on the server"
        )
        return ReadOnlyViolation(operation, resource, reason=reason)

    def _check_server_writable(self, operation: WriteOperation) -> None:
        """Refuse a write TP declares the collection incapable of.

        Args:
            operation: The attempted operation (create, update, delete)

        Raises:
            ReadOnlyViolation: The collection is read-only on the server, or
                does not accept this operation (raised in every client mode,
                before any request is sent).
        """
        if not self.server_permits(operation):
            raise self._server_refusal(operation, self.entity_type)

    async def get(
        self,
        id: int,
        *,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        result_include: list[str] | None = None,
        append: list[str] | None = None,
        innertake: int | None = None,
    ) -> T:
        """Fetch single entity by ID.

        Args:
            id: Entity ID
            include: Optional list of fields to include in response
            exclude: Optional list of fields to exclude from the response
                (server-side; the complement of ``include``)
            result_include: Optional list of fields to restrict the response
                to - server-side payload narrowing (``resultInclude=``)
            append: Optional list of calculated fields to append
                (e.g. ``["Tasks-Count"]``)
            innertake: Optional bound on the size of nested collections
                hydrated via ``include``

        Returns:
            Entity instance of type T

        Raises:
            ValueError: ``innertake`` is negative, or ``include`` names a
                field this collection cannot hydrate (see
                ``unhydratable_includes``)
            NotFoundError: Entity not found
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        self.check_include(include)
        data = await self._request_handler.get(
            self.entity_type,
            id,
            include=include,
            exclude=exclude,
            result_include=result_include,
            append=append,
            innertake=innertake,
        )
        return ResponseParser.parse_single(data, self.model_class)

    async def list(
        self,
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
    ) -> AsyncIterator[T]:
        """List entities with optional filtering, sorting, and payload shaping.

        Args:
            where: TP `where=` filter expression (e.g.
                ``"(EntityState.IsFinal eq 'false')"``)
            include: Optional list of fields to include in response
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
            Entity instances of type T

        Raises:
            ValueError: Both ``order_by`` and ``order_by_desc`` were passed,
                ``skip`` is negative, ``innertake`` is negative, or
                ``include`` names a field this collection cannot hydrate
                (raised when iteration begins)
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: API errors
        """
        self.check_include(include)
        async for item_data in self._request_handler.list(
            self.entity_type,
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
            yield ResponseParser.parse_single(item_data, self.model_class)

    async def create(self, **fields: Any) -> T:
        """Create new entity.

        Requires client mode to be READWRITE.

        Args:
            **fields: Entity field values (name, description, etc.)

        Returns:
            Created entity instance of type T

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
        self._check_server_writable("create")
        self._client._check_write_permission()
        data = await self._request_handler.create(self.entity_type, fields)
        return ResponseParser.parse_single(data, self.model_class)

    async def update(self, id: int, **fields: Any) -> T:
        """Update existing entity.

        Requires client mode to be READWRITE.

        Args:
            id: Entity ID
            **fields: Entity field values to update

        Returns:
            Updated entity instance of type T

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
        self._check_server_writable("update")
        self._client._check_write_permission()
        data = await self._request_handler.update(self.entity_type, id, fields)
        return ResponseParser.parse_single(data, self.model_class)

    async def delete(self, id: int) -> None:
        """Delete entity.

        Requires client mode to be READWRITE.

        Args:
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
        self._check_server_writable("delete")
        self._client._check_write_permission()
        await self._request_handler.delete(self.entity_type, id)

    # Return annotations on methods defined after ``list`` above must spell
    # ``builtins.list``: in class scope the method name shadows the builtin.
    async def create_many(self, items: Sequence[dict[str, Any]]) -> builtins.list[T]:
        """Create several entities in one bulk request.

        Requires client mode to be READWRITE. The whole batch is sent as a
        single ``POST /{collection}/bulk`` request - one slot against the
        rate limiter instead of one per entity.

        On the wire, a bulk item carrying an ``Id`` is an update, so every
        item here must be ``Id``-less; one that isn't raises ``ValueError``
        before any request is sent (a caller who asked to create must not
        silently overwrite an existing entity). Use :meth:`update_many` for
        updates.

        TargetProcess does not document whether a failed bulk request is
        atomic, and like every mutation it is never auto-retried - after an
        error a caller must not assume nothing was created. An empty
        ``items`` returns ``[]`` without a network request (after the write
        gates have run).

        Args:
            items: Field dicts, one per entity to create, in the wire shape
                ``create``'s keyword arguments take (e.g.
                ``{"Name": "Story", "Project": {"Id": 42}}``)

        Returns:
            The created entities, parsed as type T, as the API returned them.

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
        self._check_server_writable("create")
        self._client._check_write_permission()
        items = list(items)  # materialise once: validated and sent as the same batch
        _require_no_ids(items)
        data = await self._request_handler.bulk(self.entity_type, items)
        return [ResponseParser.parse_single(item, self.model_class) for item in data]

    async def update_many(self, items: Sequence[dict[str, Any]]) -> builtins.list[T]:
        """Update several entities in one bulk request.

        Requires client mode to be READWRITE. The whole batch is sent as a
        single ``POST /{collection}/bulk`` request - one slot against the
        rate limiter instead of one per entity.

        On the wire, a bulk item without an ``Id`` is a create, so every
        item here must carry one; one that doesn't raises ``ValueError``
        before any request is sent (a caller who asked to update must not
        silently create a new entity). Use :meth:`create_many` for creates.

        TargetProcess does not document whether a failed bulk request is
        atomic, and like every mutation it is never auto-retried - after an
        error a caller must not assume nothing was updated. An empty
        ``items`` returns ``[]`` without a network request (after the write
        gates have run).

        Args:
            items: Field dicts, one per entity to update, each carrying the
                target's ``Id`` alongside the fields to change (e.g.
                ``{"Id": 123, "Name": "Renamed"}``)

        Returns:
            The updated entities, parsed as type T, as the API returned them.

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
        self._check_server_writable("update")
        self._client._check_write_permission()
        items = list(items)  # materialise once: validated and sent as the same batch
        _require_ids(items)
        items = [_with_canonical_id(item) for item in items]
        data = await self._request_handler.bulk(self.entity_type, items)
        return [ResponseParser.parse_single(item, self.model_class) for item in data]
