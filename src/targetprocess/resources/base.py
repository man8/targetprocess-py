"""Base resource class for all TargetProcess entity resources."""

import builtins
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal

from targetprocess.exceptions import (
    AmbiguousMatchError,
    NotFoundError,
    ReadOnlyViolation,
    VerificationError,
)
from targetprocess.models import Entity, NamedEntity
from targetprocess.resources._verify import compare_fields, describe
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


def _verification_ids(items: Sequence[dict[str, Any]]) -> list[int]:
    """Return each item's ``Id`` as an integer, refusing a batch verification cannot key.

    A verified ``update_many`` keys every mismatch, and every verified Id, by the
    entity's integer Id, so a digit string such as ``"5"`` and the integer ``5``
    name one entity. An entity named twice in one batch has no single requested
    state to verify against, so that is refused rather than guessed.

    Args:
        items: The batch, each item already keyed ``Id``

    Returns:
        The items' Ids as integers, in item order.

    Raises:
        ValueError: An item's ``Id`` is neither an integer nor a string of
            digits, or two items name the same entity.
    """
    ids: list[int] = []
    for position, item in enumerate(items):
        value = item["Id"]
        if isinstance(value, str) and value.strip().isdecimal():
            entity_id = int(value)
        elif isinstance(value, int) and not isinstance(value, bool):
            entity_id = value
        else:
            raise ValueError(
                f"update_many item {position} has Id {value!r}; verify=True needs an integer Id"
            )
        if entity_id in ids:
            raise ValueError(
                f"update_many items {ids.index(entity_id)} and {position} both name Id "
                f"{entity_id}; a verified batch must name each entity once"
            )
        ids.append(entity_id)
    return ids


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


# The where= paths TargetProcess accepts and silently ignores on every collection
# whose entity type is an Assignable, keyed by the path's leading collection
# segment and mapped to the reason and the route to use instead. This is the one
# place the known set is declared: the assignable managers reference it and the
# generic entities path mirrors it. An entry is added only with live evidence -
# an unfiltered control returning the same rows.
ASSIGNABLE_IGNORED_FILTER_PATHS: dict[str, str] = {
    "Assignments": (
        "TargetProcess accepts a filter on the Assignments collection and "
        "ignores it, answering HTTP 200 with the unfiltered rows; query the "
        "join entity instead - client.assignments.list("
        'where="GeneralUser.Id eq <id>", include=["Assignable"]) - and read '
        "the work item off each assignment's assignable"
    ),
}


# A quoted value in a where= expression is data rather than a path, so it is
# blanked before matching: a literal such as 'Assignments.cs' never reads as one.
_QUOTED_VALUE = re.compile(r"'[^']*'|\"[^\"]*\"")


def check_filter_paths(where: str | None, ignored: Mapping[str, str], *, resource: str) -> None:
    """Refuse a ``where=`` filter naming a path TargetProcess is known to ignore.

    A name in ``ignored`` matches only as the leading segment of a dotted
    path, in any casing: never preceded by a word character or a dot, and
    followed by a dot. Quoted values are data, not paths, and are skipped.
    So ``(Assignments.GeneralUser.Id eq 5)`` is caught by the key
    ``Assignments``, while ``TeamAssignments.Team.Id``, ``Assignment.Id``,
    ``Owner.Assignments.Id`` and ``Name contains 'Assignments.cs'`` are not.

    Args:
        where: The ``where=`` expression a caller passed, if any
        ignored: Leading path segment -> why TargetProcess ignores a filter
            on it, and the route to use instead
        resource: The entity type name to report - the class's own for a
            typed resource, the caller's spelling on the generic path

    Raises:
        ValueError: ``where`` names a path in ``ignored``; the message says
            why and what to use instead.
    """
    if not where or not ignored:
        return
    paths = _QUOTED_VALUE.sub("''", where)
    for name, reason in ignored.items():
        if re.search(rf"(?<![\w.]){re.escape(name)}\.", paths, re.IGNORECASE):
            raise ValueError(f"where={where!r} is not supported on {resource}: {reason}")


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
        ignored_filter_paths: Leading ``where=`` path segments TP accepts
            and silently ignores on this collection, each mapped to the
            reason and the route to use instead; ``list`` refuses them with
            ``ValueError`` before any request is sent.
    """

    entity_type: str  # Override in subclass
    model_class: type[T]  # Override in subclass
    # Wire field name -> why it cannot be hydrated on this collection (and the
    # route to use instead). get() and list() refuse an include= naming one
    # before any request is sent, because TP would answer with a shape the
    # model cannot parse. Empty on every collection but the ones that collide.
    unhydratable_includes: dict[str, str] = {}
    # Leading where= path segment -> why TP accepts a filter on it and ignores
    # it (and the route to use instead). list() refuses a where= naming one
    # before any request is sent, because TP would answer HTTP 200 with the
    # unfiltered rows. Empty on every collection but the assignable ones.
    ignored_filter_paths: dict[str, str] = {}
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
    def check_where(cls, where: str | None) -> None:
        """Refuse a ``where=`` naming a path this collection silently ignores.

        Applies :func:`check_filter_paths` with ``ignored_filter_paths``. A
        collection with nothing declared there accepts every filter, as
        before.

        Args:
            where: The ``where=`` expression a caller passed, if any

        Raises:
            ValueError: ``where`` names a path in ``ignored_filter_paths``;
                the message says why and what to use instead.
        """
        check_filter_paths(where, cls.ignored_filter_paths, resource=cls.entity_type)

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
                ``skip`` is negative, ``innertake`` is negative, ``include``
                names a field this collection cannot hydrate, or ``where``
                names a path TP silently ignores on it (see
                ``ignored_filter_paths``) (raised when iteration begins)
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: API errors
        """
        self.check_include(include)
        self.check_where(where)
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

    async def update(self, id: int, *, verify: bool = False, **fields: Any) -> T:
        """Update existing entity.

        Requires client mode to be READWRITE.

        By default the return value is TP's own response to the write - its
        echo of the entity, which can be stale, so reading it can show a
        change that did not land. ``verify=True`` does not trust it: after the
        write, one independent GET re-reads the entity narrowed to the
        requested keys (``include=`` those keys, so a field outside the
        default projection such as ``CustomFields`` still arrives), compares
        each requested field with what was read back, and returns the re-read
        model - never the echo. That model carries only the requested keys:
        every field outside them is ``None``, so fetch the entity again for a
        full read. The comparison rules are those of
        :mod:`targetprocess.resources._verify`: references by ``Id``, ``None``
        against null or an absent key, numbers numerically, strings stripped,
        wire dates on the instant, custom fields by name. A key the re-read
        does not carry cannot verify, so a field TP never returns
        (``Password``) always raises.

        A ``Description`` sent without the ``<!--markdown-->`` marker is
        stored through TP's HTML pipeline and read back entity-encoded, so a
        verify on such a value can mismatch on its own encoding: prefix the
        marker, or verify on other fields.

        Args:
            id: Entity ID
            verify: Re-read the entity after the write and raise when it does
                not show the requested fields (default False)
            **fields: Entity field values to update

        Returns:
            Updated entity instance of type T - the re-read, narrowed to the
            requested keys, when ``verify`` is True; TP's echo of the write
            otherwise

        Raises:
            ValueError: ``verify`` is True and a requested key is a field
                this collection cannot hydrate (raised before the write)
            VerificationError: ``verify`` is True and the re-read does not
                show every requested field
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
        if verify:
            self.check_include(list(fields))
        data = await self._request_handler.update(self.entity_type, id, fields)
        if verify:
            return await self._verify_update(id, fields)
        return ResponseParser.parse_single(data, self.model_class)

    async def _reread_mismatches(
        self, id: int, fields: Mapping[str, Any]
    ) -> tuple[T, dict[str, tuple[Any, Any]]]:
        """Re-read one entity narrowed to ``fields`` and compare it with them.

        Args:
            id: Entity ID
            fields: The fields the write sent

        Returns:
            The re-read model, and field -> ``(requested, observed)`` for
            each field that did not verify.
        """
        data = await self._request_handler.get(self.entity_type, id, include=list(fields))
        return ResponseParser.parse_single(data, self.model_class), compare_fields(fields, data)

    async def _verify_update(self, id: int, fields: Mapping[str, Any]) -> T:
        """Re-read one updated entity and raise unless it shows ``fields``.

        Args:
            id: Entity ID
            fields: The fields the update sent

        Returns:
            The re-read entity.

        Raises:
            VerificationError: A requested field was not observed.
        """
        model, mismatches = await self._reread_mismatches(id, fields)
        if mismatches:
            by_entity = {id: mismatches}
            raise VerificationError(
                f"update did not verify - {describe(self.entity_type, by_entity)}",
                entity_type=self.entity_type,
                entity_id=id,
                mismatches=by_entity,
            )
        return model

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

    async def update_many(
        self, items: Sequence[dict[str, Any]], *, verify: bool = False
    ) -> builtins.list[T]:
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

        ``verify=True`` applies :meth:`update`'s verification to every item:
        after the whole batch has been sent, one independent GET per entity
        re-reads it narrowed to that item's keys, so each returned model
        carries only those keys. Every item is checked before anything is
        raised, so one ``VerificationError`` carries each failing entity's
        mismatches, keyed by integer Id, and the Ids that did verify. A
        verified batch must name each entity once by an integer Id (a string
        of digits counts): an entity named twice has no single requested
        state, and either is refused before any request is sent.

        Args:
            items: Field dicts, one per entity to update, each carrying the
                target's ``Id`` alongside the fields to change (e.g.
                ``{"Id": 123, "Name": "Renamed"}``)
            verify: Re-read each entity after the batch and raise when any
                does not show its requested fields (default False)

        Returns:
            The updated entities, parsed as type T - in item order as re-read
            (narrowed to each item's keys) when ``verify`` is True, as the API
            returned them otherwise.

        Raises:
            ValueError: An item has no ``Id`` key; or ``verify`` is True and an
                item's ``Id`` is not an integer, two items name the same
                entity, or an item names a field this collection cannot
                hydrate (all raised before any request is sent).
            VerificationError: ``verify`` is True and at least one re-read
                does not show its item's fields.
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
        ids: builtins.list[int] = []
        if verify:
            ids = _verification_ids(items)
            for item in items:
                self.check_include([key for key in item if key != "Id"])
        data = await self._request_handler.bulk(self.entity_type, items)
        if verify:
            return await self._verify_many(items, ids)
        return [ResponseParser.parse_single(item, self.model_class) for item in data]

    async def _verify_many(
        self, items: Sequence[dict[str, Any]], ids: Sequence[int]
    ) -> builtins.list[T]:
        """Re-read every entity of a bulk update and raise unless all show their fields.

        Args:
            items: The batch as sent, each item keyed ``Id``
            ids: The items' Ids as integers, in item order (see
                :func:`_verification_ids`)

        Returns:
            The re-read entities, in item order.

        Raises:
            VerificationError: At least one entity did not show its fields;
                raised after every item has been re-read.
        """
        models: builtins.list[T] = []
        mismatches: dict[int, dict[str, tuple[Any, Any]]] = {}
        for entity_id, item in zip(ids, items, strict=True):
            fields = {key: value for key, value in item.items() if key != "Id"}
            model, failed = await self._reread_mismatches(entity_id, fields)
            models.append(model)
            if failed:
                mismatches[entity_id] = failed
        if mismatches:
            raise VerificationError(
                f"update_many did not verify {len(mismatches)} of {len(items)} entities - "
                f"{describe(self.entity_type, mismatches)}",
                entity_type=self.entity_type,
                mismatches=mismatches,
                verified_ids=[entity_id for entity_id in ids if entity_id not in mismatches],
            )
        return models

    async def set_custom_field(
        self, id: int, name: str, value: object, *, verify: bool = True
    ) -> T:
        """Set or clear one custom-field value on an entity.

        Requires client mode to be READWRITE. TP addresses a custom-field
        value by the field's name inside the entity's ``CustomFields`` array,
        so this sends ``{"CustomFields": [{"Name": name, "Value": value}]}``
        through :meth:`update` - the same gates and the same verification.
        ``None`` clears the value: the payload carries ``"Value": null``. A
        clear has to be sent, not left out, because a partial update that
        omits a custom field leaves its value in place and still answers with
        a success status.

        Verification is on by default here, unlike :meth:`update`, because a
        discarded custom-field write is otherwise silent. The re-read requests
        ``include=[CustomFields]``, finds the entry whose name matches
        ``name`` case-insensitively, and compares its value; a cleared field
        reads back as null or an empty string, and either counts. A name that
        is misspelt, or belongs to another process's configuration, reads
        back no entry at all and raises too. Values are compared as sent, with
        no conversion between forms: a date-typed field reads back as a
        ``/Date(ms±HHMM)/`` wire string, so it verifies only when the value
        is sent in that form (:func:`targetprocess.models.format_tp_date`) -
        otherwise pass ``verify=False``.

        Args:
            id: Entity ID
            name: The custom field's name, as configured on the entity's
                process
            value: The value to set, in the wire form the field's type takes;
                ``None`` clears it
            verify: Re-read the entity and raise when the value is not
                observed (default True)

        Returns:
            The entity - the re-read, carrying only ``custom_fields``, when
            ``verify`` is True; TP's echo of the write otherwise.

        Raises:
            VerificationError: ``verify`` is True and the re-read shows a
                different value, a non-empty value after a clear, or no entry
                of that name.
            ValueError: ``verify`` is True and this collection cannot hydrate
                ``CustomFields`` (raised before the write).
            ReadOnlyViolation: Client is in readonly mode, or the collection
                is read-only on the server (any mode)
            NotFoundError: Entity not found
            RequestValidationError: TP refused the value
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        return await self.update(id, CustomFields=[{"Name": name, "Value": value}], verify=verify)
