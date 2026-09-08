"""Tests for EntityStatesResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import EntityState
from targetprocess.resources.entity_states import EntityStatesResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_entity_states_resource_entity_type():
    """Test EntityStatesResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = EntityStatesResource(mock_client, mock_request_handler)

    assert resource.entity_type == "EntityState"
    assert resource.model_class == EntityState


@pytest.mark.asyncio
async def test_entity_states_inherits_crud():
    """Test EntityStatesResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = EntityStatesResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
