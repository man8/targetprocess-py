"""TeamIteration resource manager."""

from targetprocess.models import TeamIteration
from targetprocess.resources.base import BaseResource


class TeamIterationsResource(BaseResource[TeamIteration]):
    """Resource manager for TeamIteration (team sprint) entities.

    In TP each team owns its own iterations, so a sprint is found by team:
    ``where="Team.Id eq 51"`` narrows to one team's sprints and ``IsCurrent``
    marks the one in progress. The collection is writable on the server, so
    the full CRUD surface applies.

    Example:
        client = TargetProcessClient(...)
        async for sprint in client.team_iterations.list(
            where="(Team.Id eq 51) and (IsCurrent eq 'true')", include=["Team", "Release"]
        ):
            print(sprint.name, sprint.start_date, sprint.end_date)
    """

    entity_type = "TeamIteration"
    model_class = TeamIteration
