"""Tests for BugsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import Bug
from targetprocess.resources.bugs import BugsResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_bugs_resource_entity_type():
    """Test BugsResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = BugsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Bug"
    assert resource.model_class == Bug


@pytest.mark.asyncio
async def test_bugs_inherits_crud():
    """Test BugsResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = BugsResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
