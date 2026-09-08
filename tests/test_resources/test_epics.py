"""Tests for EpicsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import Epic
from targetprocess.resources.epics import EpicsResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_epics_resource_entity_type():
    """Test EpicsResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = EpicsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Epic"
    assert resource.model_class == Epic


@pytest.mark.asyncio
async def test_epics_inherits_crud():
    """Test EpicsResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = EpicsResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
