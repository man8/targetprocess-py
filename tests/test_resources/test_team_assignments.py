"""Tests for TeamAssignmentsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import ClientMode, ReadOnlyViolation, TargetProcessClient
from targetprocess.models import TeamAssignment
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.team_assignments import TeamAssignmentsResource


@pytest.mark.asyncio
async def test_team_assignments_resource_entity_type():
    """Test TeamAssignmentsResource has correct entity_type."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = TeamAssignmentsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "TeamAssignment"
    assert resource.model_class == TeamAssignment


@pytest.mark.asyncio
async def test_team_assignments_create_parses_team_assignment():
    """Test create() delegates to the handler and parses a TeamAssignment."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.create.return_value = {
        "Id": 80816,
        "ResourceType": "TeamAssignment",
        "Team": {"Id": 214, "Name": "Ops"},
        "Assignable": {"Id": 247, "Name": "Story A"},
    }

    resource = TeamAssignmentsResource(mock_client, mock_request_handler)

    result = await resource.create(Team={"Id": 214}, Assignable={"Id": 247})

    assert isinstance(result, TeamAssignment)
    assert result.id == 80816
    assert result.team is not None and result.team.name == "Ops"
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.create.assert_called_once_with(
        "TeamAssignment", {"Team": {"Id": 214}, "Assignable": {"Id": 247}}
    )


@pytest.mark.asyncio
async def test_team_assignments_writes_blocked_in_readonly_mode():
    """Test the full write path raises ReadOnlyViolation on a READONLY client."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(ReadOnlyViolation):
        await client.team_assignments.create(Team={"Id": 1}, Assignable={"Id": 2})
    with pytest.raises(ReadOnlyViolation):
        await client.team_assignments.update(123, Team={"Id": 3})
    with pytest.raises(ReadOnlyViolation):
        await client.team_assignments.delete(123)
