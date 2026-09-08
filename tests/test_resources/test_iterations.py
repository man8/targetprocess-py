"""Tests for IterationsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import Iteration
from targetprocess.resources.iterations import IterationsResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_iterations_resource_entity_type():
    """Test IterationsResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = IterationsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Iteration"
    assert resource.model_class == Iteration


@pytest.mark.asyncio
async def test_iterations_inherits_crud():
    """Test IterationsResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = IterationsResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
