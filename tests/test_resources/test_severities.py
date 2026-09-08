"""Tests for SeveritiesResource (resolve() is covered in test_lookup_resolvers.py)."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import RequestHandler, TargetProcessClient
from targetprocess.models import Severity
from targetprocess.resources.severities import SeveritiesResource


def test_severities_resource_entity_type():
    resource = SeveritiesResource(Mock(spec=TargetProcessClient), AsyncMock(spec=RequestHandler))
    assert resource.entity_type == "Severity"
    assert resource.model_class == Severity
    # /meta: CanCreate, CanUpdate and CanDelete all true.
    assert all(SeveritiesResource.server_permits(op) for op in ("create", "update", "delete"))


@pytest.mark.asyncio
async def test_severities_update_parses_severity():
    """update() delegates to the handler and parses the ranked record back."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.update.return_value = {
        "Id": 3,
        "ResourceType": "Severity",
        "Name": "Average",
        "Importance": 3,
        "IsDefault": True,
        "IsMostImportant": False,
        "IsLeastImportant": False,
    }

    resource = SeveritiesResource(mock_client, mock_request_handler)

    result = await resource.update(3, IsDefault=True)

    assert isinstance(result, Severity)
    assert result.importance == 3
    assert result.is_default is True
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.update.assert_called_once_with("Severity", 3, {"IsDefault": True})
