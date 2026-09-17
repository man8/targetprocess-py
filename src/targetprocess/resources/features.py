"""Feature resource manager."""

from targetprocess.models import Feature
from targetprocess.resources.assignables import AssignableResource


class FeaturesResource(AssignableResource[Feature]):
    """Resource manager for Feature entities.

    Provides type-safe CRUD operations for features.

    A ``where=`` on the ``Assignments`` collection is refused before any
    request, since TargetProcess ignores it - query ``client.assignments``
    instead.

    Example:
        client = TargetProcessClient(...)
        feature = await client.features.get(123)
        async for feature in client.features.list(limit=10):
            print(feature.name)
    """

    entity_type = "Feature"
    model_class = Feature
