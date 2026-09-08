"""Assignment resource manager."""

from targetprocess.models import Assignment
from targetprocess.resources.base import BaseResource


class AssignmentsResource(BaseResource[Assignment]):
    """Resource manager for Assignment entities.

    An Assignment pairs a user (``GeneralUser``) with a ``Role`` on an
    ``Assignable`` - the authoritative record of who is assigned to a work
    item and in which capacity. Creating one takes the three references;
    removing one deletes the Assignment record itself.

    Example:
        client = TargetProcessClient(...)
        async for a in client.assignments.list(
            where="Assignable.Id eq 123",
            include=["GeneralUser", "Role", "Assignable"],
        ):
            print(a.general_user, a.role)
        role = await client.roles.resolve("Developer")
        await client.assignments.create(
            Assignable={"Id": 123}, GeneralUser={"Id": 6}, Role={"Id": role.id}
        )
    """

    entity_type = "Assignment"
    model_class = Assignment
