"""Tests for CustomFieldsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import RequestHandler, TargetProcessClient
from targetprocess.models import CustomField
from targetprocess.resources.custom_fields import CustomFieldsResource


def test_custom_fields_resource_entity_type():
    resource = CustomFieldsResource(Mock(spec=TargetProcessClient), AsyncMock(spec=RequestHandler))
    assert resource.entity_type == "CustomField"
    assert resource.model_class == CustomField
    # /meta: CanCreate, CanUpdate and CanDelete all true.
    assert all(CustomFieldsResource.server_permits(op) for op in ("create", "update", "delete"))


@pytest.mark.asyncio
async def test_custom_fields_create_parses_the_definition():
    """create() delegates to the handler and parses the definition, Config included."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.create.return_value = {
        "Id": 9,
        "ResourceType": "CustomField",
        "Name": "SampleField",
        "FieldType": "DropDown",
        "Value": "A\nB",
        "Required": False,
        "Config": {"ResourceType": "CustomFieldConfig", "DefaultValue": "A"},
        "EntityType": {"ResourceType": "EntityType", "Id": 4, "Name": "UserStory"},
        "Process": {"ResourceType": "Process", "Id": 2, "Name": "Scrum"},
    }

    resource = CustomFieldsResource(mock_client, mock_request_handler)

    result = await resource.create(
        Name="SampleField",
        FieldType="DropDown",
        Value="A\nB",
        EntityType={"Id": 4},
        Process={"Id": 2},
    )

    assert isinstance(result, CustomField)
    assert result.id == 9
    assert result.field_type == "DropDown"
    assert result.config is not None and result.config.default_value == "A"
    assert result.entity_type is not None and result.entity_type.id == 4
    assert result.process is not None and result.process.name == "Scrum"
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.create.assert_called_once_with(
        "CustomField",
        {
            "Name": "SampleField",
            "FieldType": "DropDown",
            "Value": "A\nB",
            "EntityType": {"Id": 4},
            "Process": {"Id": 2},
        },
    )
