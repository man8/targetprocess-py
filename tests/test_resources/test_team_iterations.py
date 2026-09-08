"""Tests for TeamIterationsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import ClientMode, RequestHandler, TargetProcessClient
from targetprocess.models import TeamIteration
from targetprocess.resources.team_iterations import TeamIterationsResource
from tests._support.request_handler import scripted_list


def test_team_iterations_resource_entity_type():
    resource = TeamIterationsResource(
        Mock(spec=TargetProcessClient), AsyncMock(spec=RequestHandler)
    )
    assert resource.entity_type == "TeamIteration"
    assert resource.model_class == TeamIteration
    # /meta: CanCreate, CanUpdate and CanDelete all true.
    assert all(TeamIterationsResource.server_permits(op) for op in ("create", "update", "delete"))


@pytest.mark.asyncio
async def test_team_iterations_create_parses_team_iteration():
    """create() delegates to the handler and parses the sprint with its Team reference."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.create.return_value = {
        "Id": 68611,
        "ResourceType": "TeamIteration",
        "Name": "Sprint 42",
        "StartDate": "/Date(1804460400000+0100)/",
        "EndDate": "/Date(1805497199000+0100)/",
        "IsCurrent": False,
        "Team": {"Id": 51642, "Name": "Sample Team"},
    }

    resource = TeamIterationsResource(mock_client, mock_request_handler)

    result = await resource.create(
        Name="Sprint 42",
        Team={"Id": 51642},
        StartDate="/Date(1804460400000+0100)/",
        EndDate="/Date(1805497199000+0100)/",
    )

    assert isinstance(result, TeamIteration)
    assert result.id == 68611
    assert result.is_current is False
    assert result.team is not None and result.team.id == 51642
    assert result.start_date is not None and result.start_date.year == 2027
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.create.assert_called_once_with(
        "TeamIteration",
        {
            "Name": "Sprint 42",
            "Team": {"Id": 51642},
            "StartDate": "/Date(1804460400000+0100)/",
            "EndDate": "/Date(1805497199000+0100)/",
        },
    )


@pytest.mark.asyncio
async def test_team_iterations_list_forwards_the_team_filter():
    """A team-scoped listing passes its where= through verbatim."""
    _list, seen = scripted_list(
        [{"Id": 1, "ResourceType": "TeamIteration", "Name": "Sprint 1", "IsCurrent": True}]
    )
    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READONLY
    handler = Mock(spec=RequestHandler)
    handler.list = _list
    resource = TeamIterationsResource(client, handler)

    sprints = [s async for s in resource.list(where="(Team.Id eq 51) and (IsCurrent eq 'true')")]

    assert seen["entity_type"] == "TeamIteration"
    assert seen["where"] == "(Team.Id eq 51) and (IsCurrent eq 'true')"
    assert len(sprints) == 1 and sprints[0].is_current is True
