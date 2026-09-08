"""Iteration resource manager."""

from targetprocess.models import Iteration
from targetprocess.resources.base import BaseResource


class IterationsResource(BaseResource[Iteration]):
    """Resource manager for Iteration entities.

    Provides type-safe CRUD operations for iterations.

    Example:
        client = TargetProcessClient(...)
        iteration = await client.iterations.get(123)
        async for iteration in client.iterations.list(limit=10):
            print(iteration.name)
    """

    entity_type = "Iteration"
    model_class = Iteration
