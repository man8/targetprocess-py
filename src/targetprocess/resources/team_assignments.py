"""TeamAssignment resource manager."""

from targetprocess.models import TeamAssignment
from targetprocess.resources.base import BaseResource


class TeamAssignmentsResource(BaseResource[TeamAssignment]):
    """Resource manager for TeamAssignment entities.

    A TeamAssignment assigns a Team to an Assignable over a time window.

    Example:
        client = TargetProcessClient(...)
        async for ta in client.team_assignments.list(
            where="Assignable.Id eq 123", include=["Team", "Assignable"]
        ):
            print(ta.team)
    """

    entity_type = "TeamAssignment"
    model_class = TeamAssignment
