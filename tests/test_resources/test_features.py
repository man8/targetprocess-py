"""Tests for FeaturesResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import Feature
from targetprocess.resources.features import FeaturesResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_features_resource_entity_type():
    """Test FeaturesResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = FeaturesResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Feature"
    assert resource.model_class == Feature


@pytest.mark.asyncio
async def test_features_inherits_crud():
    """Test FeaturesResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = FeaturesResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
