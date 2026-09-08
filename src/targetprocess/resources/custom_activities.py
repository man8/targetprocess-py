"""CustomActivity resource manager."""

from targetprocess.models import CustomActivity
from targetprocess.resources.base import BaseResource, _resolve_by_name


class CustomActivitiesResource(BaseResource[CustomActivity]):
    """Resource manager for CustomActivity entities.

    A custom activity is the non-work-item target for time tracking: a
    ``Time`` record references one instead of an ``Assignable`` (see
    ``Time.custom_activity``). Activities are scoped to a project and a
    user, so ``resolve`` refuses a name that several projects share rather
    than guessing between them. The collection is writable on the server, so
    the full CRUD surface applies.

    Example:
        client = TargetProcessClient(...)
        meetings = await client.custom_activities.resolve("Meetings")
        async for entry in client.times.list(where=f"CustomActivity.Id eq {meetings.id}"):
            print(entry.spent)
    """

    entity_type = "CustomActivity"
    model_class = CustomActivity

    async def resolve(self, name: str) -> CustomActivity:
        """Resolve a custom-activity name to its single CustomActivity record.

        Matching is case-insensitive. A name matching zero or several records
        raises rather than picking a candidate, so an ambiguous resolution
        never reaches the API - and because activities are project-scoped, a
        name shared across projects is exactly the ambiguous case.

        This issues one HTTP request per call; callers resolving several
        activities should call ``list()`` once and match locally instead of
        calling ``resolve()`` in a loop.

        Args:
            name: Custom-activity display name (e.g. ``"Meetings"``)

        Returns:
            The single matching CustomActivity.

        Raises:
            NotFoundError: No custom activity of that name exists (the
                message lists the names that do).
            AmbiguousMatchError: More than one custom activity of that name
                matched.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        return _resolve_by_name([a async for a in self.list()], name, what="custom activity")
