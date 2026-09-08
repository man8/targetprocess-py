"""Tests for TeamsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import Team
from targetprocess.resources.teams import TeamsResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_teams_resource_entity_type():
    """Test TeamsResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = TeamsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Team"
    assert resource.model_class == Team


@pytest.mark.asyncio
async def test_teams_inherits_crud():
    """Test TeamsResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = TeamsResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
