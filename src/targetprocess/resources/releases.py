"""Release resource manager."""

from targetprocess.models import Release
from targetprocess.resources.base import BaseResource


class ReleasesResource(BaseResource[Release]):
    """Resource manager for Release entities.

    Provides type-safe CRUD operations for releases.

    Example:
        client = TargetProcessClient(...)
        release = await client.releases.get(123)
        async for release in client.releases.list(limit=10):
            print(release.name)
    """

    entity_type = "Release"
    model_class = Release
