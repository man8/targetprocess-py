"""Request resource manager."""

from targetprocess.models import Request
from targetprocess.resources.base import ASSIGNABLE_IGNORED_FILTER_PATHS, BaseResource


class RequestsResource(BaseResource[Request]):
    """Resource manager for Request entities.

    Provides type-safe CRUD operations for requests.

    A ``where=`` on the ``Assignments`` collection is refused before any
    request, since TargetProcess ignores it - query ``client.assignments``
    instead.

    Example:
        client = TargetProcessClient(...)
        request = await client.requests.get(123)
        async for request in client.requests.list(limit=10):
            print(request.name)
    """

    entity_type = "Request"
    model_class = Request
    ignored_filter_paths = ASSIGNABLE_IGNORED_FILTER_PATHS
