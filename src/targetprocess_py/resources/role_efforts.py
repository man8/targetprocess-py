"""RoleEffort resource manager."""

from targetprocess_py.models import RoleEffort
from targetprocess_py.resources.base import BaseResource


class RoleEffortsResource(BaseResource[RoleEffort]):
    """Resource manager for RoleEffort entities.

    A RoleEffort breaks an Assignable's effort down by Role, and it is where
    that effort is *stored*: an Assignable's ``Effort``, ``EffortCompleted``
    and ``EffortToDo`` are **derived**, each the sum of the corresponding field
    over the item's RoleEfforts. So this collection is the route that changes a
    work item's effort, and the work-item managers refuse a direct write to the
    roll-up before any request is sent.

    One row per (Assignable, Role) pair. Setting effort for a role means
    updating that pair's row, or creating it where the role has none -
    ``list(where="Assignable.Id eq <id>", include=["Role"])`` is how to tell
    which. Unlike the roll-up, the fields *here* are stored as written, so a
    write is worth verifying rather than assuming.

    Example:
        client = TargetProcessClient(...)
        async for re in client.role_efforts.list(
            where="Assignable.Id eq 123", include=["Role", "Assignable"]
        ):
            print(re.role, re.effort)
    """

    entity_type = "RoleEffort"
    model_class = RoleEffort
