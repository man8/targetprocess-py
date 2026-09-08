"""Team resource manager."""

from targetprocess.models import Team
from targetprocess.resources.base import BaseResource


class TeamsResource(BaseResource[Team]):
    """Resource manager for Team entities.

    Provides type-safe CRUD operations for teams.

    Example:
        client = TargetProcessClient(...)
        team = await client.teams.get(123)
        async for team in client.teams.list(limit=10):
            print(team.name)
    """

    entity_type = "Team"
    model_class = Team
