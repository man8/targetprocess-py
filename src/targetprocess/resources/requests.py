"""Request resource manager."""

from targetprocess.models import Request
from targetprocess.resources.base import BaseResource


class RequestsResource(BaseResource[Request]):
    """Resource manager for Request entities.

    Provides type-safe CRUD operations for requests.

    Example:
        client = TargetProcessClient(...)
        request = await client.requests.get(123)
        async for request in client.requests.list(limit=10):
            print(request.name)
    """

    entity_type = "Request"
    model_class = Request
