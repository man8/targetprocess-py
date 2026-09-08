"""EntityType resource manager."""

from targetprocess.models import EntityType
from targetprocess.resources.base import BaseResource, _resolve_by_name


class EntityTypesResource(BaseResource[EntityType]):
    """Resource manager for EntityType lookup entities.

    The instance's own type catalogue - which types exist, which are
    assignable, which take custom fields - and so how a client discovers the
    instance's configuration at runtime. TP declares the collection itself
    read-only, and the resource enforces that client-side: ``create``,
    ``update`` and ``delete`` (and the bulk pair) raise ``ReadOnlyViolation``
    in every client mode - READWRITE included - before any request is sent.
    The resource's value is lookup and name-to-Id resolution: an entity-type
    Id keys the ``EntityStates``, ``CustomFields`` and ``Priorities``
    collections.

    Example:
        client = TargetProcessClient(...)
        story_type = await client.entity_types.resolve("UserStory")
        async for state in client.entity_states.list(
            where=f"EntityType.Id eq {story_type.id}"
        ):
            print(state.name)
    """

    entity_type = "EntityType"
    model_class = EntityType
    server_read_only = True

    async def resolve(self, name: str) -> EntityType:
        """Resolve an entity-type name to its single EntityType record.

        Matching is case-insensitive. A name matching zero or several records
        raises rather than picking a candidate, so an ambiguous resolution
        never reaches the API.

        This issues one HTTP request per call; callers resolving several
        entity types should call ``list()`` once and match locally instead
        of calling ``resolve()`` in a loop.

        Args:
            name: Entity-type name (e.g. ``"UserStory"``)

        Returns:
            The single matching EntityType.

        Raises:
            NotFoundError: No entity type of that name exists (the message
                lists the names that do).
            AmbiguousMatchError: More than one entity type of that name
                matched.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        return _resolve_by_name([t async for t in self.list()], name, what="entity type")
