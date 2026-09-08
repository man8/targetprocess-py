"""Comment resource manager."""

from targetprocess.models import Comment
from targetprocess.resources.base import BaseResource


class CommentsResource(BaseResource[Comment]):
    """Resource manager for Comment entities.

    Provides type-safe CRUD operations for comments. The comment body goes
    in ``description``; ``general`` names the entity the comment is attached
    to, so creating a comment takes ``General={"Id": <entity id>}`` alongside
    ``Description``.

    Example:
        client = TargetProcessClient(...)
        comment = await client.comments.get(123)
        async for comment in client.comments.list(limit=10):
            print(comment.description)
    """

    entity_type = "Comment"
    model_class = Comment
