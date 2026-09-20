"""UserStory resource manager."""

from targetprocess_py.models import UserStory
from targetprocess_py.resources.assignables import AssignableResource


class UserStoriesResource(AssignableResource[UserStory]):
    """Resource manager for UserStory entities.

    Provides type-safe CRUD operations for user stories.

    A ``where=`` on the ``Assignments`` collection is refused before any
    request, since TargetProcess ignores it - query ``client.assignments``
    instead.

    Example:
        client = TargetProcessClient(...)
        story = await client.user_stories.get(123)
        async for story in client.user_stories.list(limit=10):
            print(story.name)
    """

    entity_type = "UserStory"
    model_class = UserStory
