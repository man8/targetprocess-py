"""UserStory resource manager."""

from targetprocess.models import UserStory
from targetprocess.resources.base import BaseResource


class UserStoriesResource(BaseResource[UserStory]):
    """Resource manager for UserStory entities.

    Provides type-safe CRUD operations for user stories.

    Example:
        client = TargetProcessClient(...)
        story = await client.user_stories.get(123)
        async for story in client.user_stories.list(limit=10):
            print(story.name)
    """

    entity_type = "UserStory"
    model_class = UserStory
