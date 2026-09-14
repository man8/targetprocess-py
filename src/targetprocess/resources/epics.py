"""Epic resource manager."""

from targetprocess.models import Epic
from targetprocess.resources.base import ASSIGNABLE_IGNORED_FILTER_PATHS, BaseResource


class EpicsResource(BaseResource[Epic]):
    """Resource manager for Epic entities.

    Provides type-safe CRUD operations for epics.

    A ``where=`` on the ``Assignments`` collection is refused before any
    request, since TargetProcess ignores it - query ``client.assignments``
    instead.

    Example:
        client = TargetProcessClient(...)
        epic = await client.epics.get(123)
        async for epic in client.epics.list(limit=10):
            print(epic.name)
    """

    entity_type = "Epic"
    model_class = Epic
    ignored_filter_paths = ASSIGNABLE_IGNORED_FILTER_PATHS
