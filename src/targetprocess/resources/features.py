"""Feature resource manager."""

from targetprocess.models import Feature
from targetprocess.resources.base import BaseResource


class FeaturesResource(BaseResource[Feature]):
    """Resource manager for Feature entities.

    Provides type-safe CRUD operations for features.

    Example:
        client = TargetProcessClient(...)
        feature = await client.features.get(123)
        async for feature in client.features.list(limit=10):
            print(feature.name)
    """

    entity_type = "Feature"
    model_class = Feature
