"""Tests for ReleasesResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import Release
from targetprocess.resources.releases import ReleasesResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_releases_resource_entity_type():
    """Test ReleasesResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = ReleasesResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Release"
    assert resource.model_class == Release


@pytest.mark.asyncio
async def test_releases_inherits_crud():
    """Test ReleasesResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = ReleasesResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
