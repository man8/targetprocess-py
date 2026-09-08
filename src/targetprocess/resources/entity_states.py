"""EntityState resource manager."""

from targetprocess.models import EntityState
from targetprocess.resources.base import BaseResource


class EntityStatesResource(BaseResource[EntityState]):
    """Resource manager for EntityState entities.

    Provides type-safe CRUD operations for entity states.

    Example:
        client = TargetProcessClient(...)
        state = await client.entity_states.get(123)
        async for state in client.entity_states.list(limit=10):
            print(state.name)
    """

    entity_type = "EntityState"
    model_class = EntityState
