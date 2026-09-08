"""Severity resource manager."""

from targetprocess.models import Severity
from targetprocess.resources.base import BaseResource, _resolve_by_name


class SeveritiesResource(BaseResource[Severity]):
    """Resource manager for Severity lookup entities.

    Severities apply to Bugs only and are defined instance-wide, so a name is
    unique across the instance and ``resolve`` takes no entity type (compare
    ``priorities.resolve``, where names repeat per entity type). The
    collection is writable on the server, so the full CRUD surface applies.

    Example:
        client = TargetProcessClient(...)
        blocking = await client.severities.resolve("Blocking")
        bug = await client.bugs.create(
            Name="Login fails", Project={"Id": 42}, Severity={"Id": blocking.id}
        )
    """

    entity_type = "Severity"
    model_class = Severity

    async def resolve(self, name: str) -> Severity:
        """Resolve a severity name to its single Severity record.

        Matching is case-insensitive. A name matching zero or several records
        raises rather than picking a candidate, so an ambiguous resolution
        never reaches the API.

        This issues one HTTP request per call; callers resolving several
        severities should call ``list()`` once and match locally instead of
        calling ``resolve()`` in a loop.

        Args:
            name: Severity display name (e.g. ``"Blocking"``)

        Returns:
            The single matching Severity.

        Raises:
            NotFoundError: No severity of that name exists (the message
                lists the names that do).
            AmbiguousMatchError: More than one severity of that name matched.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        return _resolve_by_name([s async for s in self.list()], name, what="severity")
