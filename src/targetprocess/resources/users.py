"""User resource manager."""

from targetprocess.models import User
from targetprocess.resources.base import BaseResource


class UsersResource(BaseResource[User]):
    """Resource manager for User entities.

    Provides type-safe CRUD operations for users.

    Example:
        client = TargetProcessClient(...)
        user = await client.users.get(123)
        async for user in client.users.list(limit=10):
            print(user.full_name)
    """

    entity_type = "User"
    model_class = User
