"""RelationType resource manager."""

from targetprocess.models import RelationType
from targetprocess.resources.base import BaseResource, _resolve_by_name


class RelationTypesResource(BaseResource[RelationType]):
    """Resource manager for RelationType lookup entities.

    Relation types are defined instance-wide (Dependency, Blocker, Relation,
    Duplicate, ...), and a Relation is typed by one - so resolving a
    relation-type name to its Id is the step that makes relation payloads
    constructible. TP declares the collection itself read-only, and the
    resource enforces that client-side: ``create``, ``update`` and ``delete``
    raise ``ReadOnlyViolation`` in every client mode - READWRITE included -
    before any request is sent. The resource's value is lookup and name-to-Id
    resolution.

    Example:
        client = TargetProcessClient(...)
        blocker = await client.relation_types.resolve("Blocker")
        await client.relations.create(
            Master={"Id": 456}, Slave={"Id": 123}, RelationType={"Id": blocker.id}
        )
    """

    entity_type = "RelationType"
    model_class = RelationType
    server_read_only = True

    async def resolve(self, name: str) -> RelationType:
        """Resolve a relation-type name to its single RelationType record.

        Matching is case-insensitive. A name matching zero or several records
        raises rather than picking a candidate, so an ambiguous resolution
        never reaches the API.

        This issues one HTTP request per call; callers resolving several
        relation types should call ``list()`` once and match locally instead
        of calling ``resolve()`` in a loop.

        Args:
            name: Relation-type display name (e.g. ``"Blocker"``)

        Returns:
            The single matching RelationType.

        Raises:
            NotFoundError: No relation type of that name exists (the message
                lists the names that do).
            AmbiguousMatchError: More than one relation type of that name
                matched.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        return _resolve_by_name([rt async for rt in self.list()], name, what="relation type")
