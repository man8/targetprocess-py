"""RoleEffort resource manager."""

from targetprocess.models import RoleEffort
from targetprocess.resources.base import BaseResource


class RoleEffortsResource(BaseResource[RoleEffort]):
    """Resource manager for RoleEffort entities.

    A RoleEffort breaks an Assignable's effort down by Role.

    Example:
        client = TargetProcessClient(...)
        async for re in client.role_efforts.list(
            where="Assignable.Id eq 123", include=["Role", "Assignable"]
        ):
            print(re.role, re.effort)
    """

    entity_type = "RoleEffort"
    model_class = RoleEffort
