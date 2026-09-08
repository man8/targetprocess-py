"""Epic resource manager."""

from targetprocess.models import Epic
from targetprocess.resources.base import BaseResource


class EpicsResource(BaseResource[Epic]):
    """Resource manager for Epic entities.

    Provides type-safe CRUD operations for epics.

    Example:
        client = TargetProcessClient(...)
        epic = await client.epics.get(123)
        async for epic in client.epics.list(limit=10):
            print(epic.name)
    """

    entity_type = "Epic"
    model_class = Epic
