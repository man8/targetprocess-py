"""Tests for RoleEffortsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import ClientMode, ReadOnlyViolation, TargetProcessClient
from targetprocess.models import RoleEffort
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.role_efforts import RoleEffortsResource


@pytest.mark.asyncio
async def test_role_efforts_resource_entity_type():
    """Test RoleEffortsResource has correct entity_type."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = RoleEffortsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "RoleEffort"
    assert resource.model_class == RoleEffort


@pytest.mark.asyncio
async def test_role_efforts_update_parses_role_effort():
    """Test update() delegates to the handler and parses a RoleEffort."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.update.return_value = {
        "Id": 456100,
        "ResourceType": "RoleEffort",
        "EffortToDo": 4.0,
        "Role": {"Id": 20, "Name": "Developer"},
        "Assignable": {"Id": 51383, "Name": "Story B"},
    }

    resource = RoleEffortsResource(mock_client, mock_request_handler)

    result = await resource.update(456100, EffortToDo=4.0)

    assert isinstance(result, RoleEffort)
    assert result.id == 456100
    assert result.effort_todo == 4.0
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.update.assert_called_once_with("RoleEffort", 456100, {"EffortToDo": 4.0})


@pytest.mark.asyncio
async def test_role_efforts_writes_blocked_in_readonly_mode():
    """Test the full write path raises ReadOnlyViolation on a READONLY client."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(ReadOnlyViolation):
        await client.role_efforts.create(Assignable={"Id": 1}, Role={"Id": 2})
    with pytest.raises(ReadOnlyViolation):
        await client.role_efforts.update(123, EffortToDo=1.0)
    with pytest.raises(ReadOnlyViolation):
        await client.role_efforts.delete(123)
