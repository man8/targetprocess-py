"""Tests for CustomActivitiesResource (resolve() is covered in test_lookup_resolvers.py)."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import RequestHandler, TargetProcessClient
from targetprocess.models import CustomActivity
from targetprocess.resources.custom_activities import CustomActivitiesResource


def test_custom_activities_resource_entity_type():
    resource = CustomActivitiesResource(
        Mock(spec=TargetProcessClient), AsyncMock(spec=RequestHandler)
    )
    assert resource.entity_type == "CustomActivity"
    assert resource.model_class == CustomActivity
    # /meta: CanCreate, CanUpdate and CanDelete all true.
    assert all(CustomActivitiesResource.server_permits(op) for op in ("create", "update", "delete"))


@pytest.mark.asyncio
async def test_custom_activities_create_parses_activity():
    """create() delegates to the handler and parses the project- and user-scoped record."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.create.return_value = {
        "Id": 21,
        "ResourceType": "CustomActivity",
        "Name": "Meetings",
        "Estimate": 2.0,
        "Project": {"ResourceType": "Project", "Id": 42, "Name": "Sample Project"},
        "User": {"ResourceType": "User", "Id": 7, "FullName": "Alex Example"},
    }

    resource = CustomActivitiesResource(mock_client, mock_request_handler)

    result = await resource.create(Name="Meetings", Project={"Id": 42}, User={"Id": 7})

    assert isinstance(result, CustomActivity)
    assert result.id == 21
    assert result.estimate == 2.0
    assert result.project is not None and result.project.id == 42
    assert result.user is not None and result.user.full_name == "Alex Example"
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.create.assert_called_once_with(
        "CustomActivity", {"Name": "Meetings", "Project": {"Id": 42}, "User": {"Id": 7}}
    )
