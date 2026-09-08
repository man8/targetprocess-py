"""Tests for AssignmentsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import ClientMode, ReadOnlyViolation, TargetProcessClient
from targetprocess.models import Assignment
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.assignments import AssignmentsResource


@pytest.mark.asyncio
async def test_assignments_resource_entity_type():
    """Test AssignmentsResource has correct entity_type."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = AssignmentsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Assignment"
    assert resource.model_class == Assignment


@pytest.mark.asyncio
async def test_assignments_inherits_crud():
    """Test AssignmentsResource inherits CRUD operations."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = AssignmentsResource(mock_client, mock_request_handler)

    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")


@pytest.mark.asyncio
async def test_assignments_create_parses_assignment():
    """Test create() delegates to the handler and parses an Assignment."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.create.return_value = {
        "Id": 5501,
        "ResourceType": "Assignment",
        "GeneralUser": {"Id": 6, "Login": "alex"},
        "Role": {"Id": 1, "Name": "Developer"},
        "Assignable": {"Id": 123, "Name": "Story A"},
    }

    resource = AssignmentsResource(mock_client, mock_request_handler)

    result = await resource.create(Assignable={"Id": 123}, GeneralUser={"Id": 6}, Role={"Id": 1})

    assert isinstance(result, Assignment)
    assert result.id == 5501
    assert result.general_user is not None and result.general_user.id == 6
    assert result.role is not None and result.role.id == 1
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.create.assert_called_once_with(
        "Assignment",
        {"Assignable": {"Id": 123}, "GeneralUser": {"Id": 6}, "Role": {"Id": 1}},
    )


@pytest.mark.asyncio
async def test_assignments_writes_blocked_in_readonly_mode():
    """Test the full write path raises ReadOnlyViolation on a READONLY client."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(ReadOnlyViolation):
        await client.assignments.create(Assignable={"Id": 1}, GeneralUser={"Id": 2}, Role={"Id": 3})
    with pytest.raises(ReadOnlyViolation):
        await client.assignments.update(123, Role={"Id": 4})
    with pytest.raises(ReadOnlyViolation):
        await client.assignments.delete(123)
