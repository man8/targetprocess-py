"""Tests for EntityTypesResource.

resolve() is covered in test_lookup_resolvers.py and the server-read-only
refusals in test_server_capability.py; this file pins the class contract and
the read path.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import RequestHandler, TargetProcessClient
from targetprocess.models import EntityType
from targetprocess.resources.entity_types import EntityTypesResource


def test_entity_types_resource_entity_type():
    resource = EntityTypesResource(Mock(spec=TargetProcessClient), AsyncMock(spec=RequestHandler))
    assert resource.entity_type == "EntityType"
    assert resource.model_class == EntityType
    # /meta: CanCreate, CanUpdate and CanDelete all false.
    assert EntityTypesResource.server_read_only is True
    assert not any(EntityTypesResource.server_permits(op) for op in ("create", "update", "delete"))


@pytest.mark.asyncio
async def test_entity_types_get_parses_the_capability_flags():
    """get() parses the full record - the flags a client discovers the instance by."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.get.return_value = {
        "Id": 4,
        "ResourceType": "EntityType",
        "Name": "UserStory",
        "IsAssignable": True,
        "IsExtendable": True,
        "IsUnitInHourOnly": False,
        "CustomFieldScope": "Process",
    }

    resource = EntityTypesResource(mock_client, mock_request_handler)

    result = await resource.get(4)

    assert isinstance(result, EntityType)
    assert result.id == 4
    assert result.is_assignable is True
    assert result.is_extendable is True
    assert result.custom_field_scope == "Process"
    mock_request_handler.get.assert_awaited_once()
    assert mock_request_handler.get.call_args.args == ("EntityType", 4)
