"""Tests for CustomRulesResource.

The create/delete refusals are covered in test_server_capability.py; this file
pins the class contract and the one write TP does accept.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import RequestHandler, TargetProcessClient
from targetprocess.models import CustomRule
from targetprocess.resources.custom_rules import CustomRulesResource


def test_custom_rules_resource_entity_type():
    resource = CustomRulesResource(Mock(spec=TargetProcessClient), AsyncMock(spec=RequestHandler))
    assert resource.entity_type == "CustomRule"
    assert resource.model_class == CustomRule
    # /meta: CanCreate false, CanUpdate true, CanDelete false - the partial
    # case the per-operation flags exist for.
    assert CustomRulesResource.server_read_only is False
    assert not CustomRulesResource.server_permits("create")
    assert CustomRulesResource.server_permits("update")
    assert not CustomRulesResource.server_permits("delete")


@pytest.mark.asyncio
async def test_custom_rules_update_toggles_is_enabled():
    """update() - the one accepted write - delegates and parses the toggled rule."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.update.return_value = {
        "Id": 9,
        "ResourceType": "CustomRule",
        "Name": "Sample rule",
        "IsEnabled": False,
    }

    resource = CustomRulesResource(mock_client, mock_request_handler)

    result = await resource.update(9, IsEnabled=False)

    assert isinstance(result, CustomRule)
    assert result.id == 9
    assert result.is_enabled is False
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.update.assert_called_once_with("CustomRule", 9, {"IsEnabled": False})


@pytest.mark.asyncio
async def test_custom_rules_update_many_reaches_the_bulk_endpoint():
    """update_many() passes the update-only gate and sends one bulk request."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.bulk.return_value = [
        {"Id": 9, "ResourceType": "CustomRule", "IsEnabled": True},
        {"Id": 10, "ResourceType": "CustomRule", "IsEnabled": True},
    ]

    resource = CustomRulesResource(mock_client, mock_request_handler)

    result = await resource.update_many(
        [{"Id": 9, "IsEnabled": True}, {"Id": 10, "IsEnabled": True}]
    )

    assert [rule.id for rule in result] == [9, 10]
    assert all(rule.is_enabled for rule in result)
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.bulk.assert_called_once_with(
        "CustomRule", [{"Id": 9, "IsEnabled": True}, {"Id": 10, "IsEnabled": True}]
    )
