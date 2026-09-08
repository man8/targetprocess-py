"""Project resource manager."""

from targetprocess.models import Project
from targetprocess.resources.base import BaseResource


class ProjectsResource(BaseResource[Project]):
    """Resource manager for Project entities.

    Provides type-safe CRUD operations for projects.

    Example:
        client = TargetProcessClient(...)
        project = await client.projects.get(123)
        async for project in client.projects.list(limit=10):
            print(project.name)
    """

    entity_type = "Project"
    model_class = Project
