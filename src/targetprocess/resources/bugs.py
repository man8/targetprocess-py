"""Bug resource manager."""

from targetprocess.models import Bug
from targetprocess.resources.base import BaseResource


class BugsResource(BaseResource[Bug]):
    """Resource manager for Bug entities.

    Provides type-safe CRUD operations for bugs.

    Example:
        client = TargetProcessClient(...)
        bug = await client.bugs.get(123)
        async for bug in client.bugs.list(limit=10):
            print(bug.name)
    """

    entity_type = "Bug"
    model_class = Bug
