"""Role resource manager."""

from targetprocess.models import Role
from targetprocess.resources.base import BaseResource, _resolve_by_name


class RolesResource(BaseResource[Role]):
    """Resource manager for Role lookup entities.

    Roles are defined instance-wide (Developer, QA Engineer, ...), and an
    Assignment pairs a user with a Role - so resolving a role name to its
    Id is the step that makes assignment payloads constructible.

    Example:
        client = TargetProcessClient(...)
        role = await client.roles.resolve("Developer")
        await client.assignments.create(
            Assignable={"Id": 123}, GeneralUser={"Id": 6}, Role={"Id": role.id}
        )
    """

    entity_type = "Role"
    model_class = Role

    async def resolve(self, name: str) -> Role:
        """Resolve a role name to its single Role record.

        Matching is case-insensitive. A name matching zero or several records
        raises rather than picking a candidate, so an ambiguous resolution
        never reaches the API.

        This issues one HTTP request per call; callers resolving several
        roles should call ``list()`` once and match locally instead of
        calling ``resolve()`` in a loop.

        Args:
            name: Role display name (e.g. ``"Developer"``)

        Returns:
            The single matching Role.

        Raises:
            NotFoundError: No role of that name exists (the message lists
                the names that do).
            AmbiguousMatchError: More than one role of that name matched.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        return _resolve_by_name([r async for r in self.list()], name, what="role")
