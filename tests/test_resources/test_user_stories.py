"""Tests for UserStoriesResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import UserStory
from targetprocess.resources.user_stories import UserStoriesResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_user_stories_resource_entity_type():
    """Test UserStoriesResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = UserStoriesResource(mock_client, mock_request_handler)

    assert resource.entity_type == "UserStory"
    assert resource.model_class == UserStory


@pytest.mark.asyncio
async def test_user_stories_inherits_crud():
    """Test UserStoriesResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = UserStoriesResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
