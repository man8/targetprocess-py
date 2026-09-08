"""Priority resource manager."""

from targetprocess._entity_types import require_entity_type
from targetprocess.models import Priority
from targetprocess.resources.base import BaseResource, _resolve_by_name


class PrioritiesResource(BaseResource[Priority]):
    """Resource manager for Priority entities.

    TP scopes priorities by entity type: a Priority record carries an
    ``EntityType`` and no Project or Process reference, so the valid set
    depends only on the entity type being created, never on the project it
    lands in. Names repeat across those sets - "Must Have" exists separately
    for UserStory, Feature, Epic and PortfolioEpic - so a bare name is
    ambiguous instance-wide but unique within one entity type.

    Example:
        client = TargetProcessClient(...)
        priority = await client.priorities.resolve("Must Have", entity_type="UserStory")
        story = await client.user_stories.create(
            Name="Ship it", Project={"Id": 42}, Priority={"Id": priority.id}
        )
    """

    entity_type = "Priority"
    model_class = Priority

    async def for_entity_type(self, entity_type: str) -> list[Priority]:
        """Return every Priority valid for one TP entity type.

        Args:
            entity_type: TP entity type name (e.g. ``"UserStory"``, ``"Bug"``)

        Returns:
            The priorities defined for that entity type, in API order.

        Raises:
            ValueError: ``entity_type`` is not a valid TP entity type
                identifier (letters, digits and underscores only, not
                starting with a digit).
            RequestValidationError: TP rejected the resulting filter.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        require_entity_type(entity_type)
        return [p async for p in self.list(where=f"EntityType.Name eq '{entity_type}'")]

    async def resolve(self, name: str, *, entity_type: str) -> Priority:
        """Resolve a priority name to the one record valid for an entity type.

        Matching is case-insensitive. A name matching zero or several records
        raises rather than picking a candidate: TP answers a create carrying
        the wrong Priority Id with a misleading HTTP 403, so an ambiguous
        resolution must never reach the API.

        This issues one HTTP request per call; callers resolving several
        priorities should call ``for_entity_type()`` once and reuse the
        result instead of calling ``resolve()`` in a loop.

        Args:
            name: Priority display name (e.g. ``"Must Have"``)
            entity_type: TP entity type name (e.g. ``"UserStory"``)

        Returns:
            The single matching Priority.

        Raises:
            NotFoundError: No priority of that name exists for the entity type.
            AmbiguousMatchError: More than one priority of that name matched.
            ValueError: ``entity_type`` is not a valid TP entity type
                identifier (letters, digits and underscores only, not
                starting with a digit).
            RequestValidationError: TP rejected the resulting filter.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        candidates = await self.for_entity_type(entity_type)
        return _resolve_by_name(candidates, name, what=f"{entity_type} priority")
