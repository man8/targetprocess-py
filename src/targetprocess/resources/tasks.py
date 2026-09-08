"""Task resource manager."""

from targetprocess.models import Task
from targetprocess.resources.base import BaseResource


class TasksResource(BaseResource[Task]):
    """Resource manager for Task entities.

    Provides type-safe CRUD operations for tasks.

    Example:
        client = TargetProcessClient(...)
        task = await client.tasks.get(123)
        async for task in client.tasks.list(limit=10):
            print(task.name)
    """

    entity_type = "Task"
    model_class = Task
