"""Task resource manager."""

from targetprocess_py.models import Task
from targetprocess_py.resources.assignables import AssignableResource


class TasksResource(AssignableResource[Task]):
    """Resource manager for Task entities.

    Provides type-safe CRUD operations for tasks.

    A ``where=`` on the ``Assignments`` collection is refused before any
    request, since TargetProcess ignores it - query ``client.assignments``
    instead.

    Example:
        client = TargetProcessClient(...)
        task = await client.tasks.get(123)
        async for task in client.tasks.list(limit=10):
            print(task.name)
    """

    entity_type = "Task"
    model_class = Task
