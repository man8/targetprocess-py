"""Bug resource manager."""

from targetprocess.models import Bug
from targetprocess.resources.assignables import AssignableResource


class BugsResource(AssignableResource[Bug]):
    """Resource manager for Bug entities.

    Provides type-safe CRUD operations for bugs.

    A ``where=`` on the ``Assignments`` collection is refused before any
    request, since TargetProcess ignores it - query ``client.assignments``
    instead.

    Example:
        client = TargetProcessClient(...)
        bug = await client.bugs.get(123)
        async for bug in client.bugs.list(limit=10):
            print(bug.name)
    """

    entity_type = "Bug"
    model_class = Bug
