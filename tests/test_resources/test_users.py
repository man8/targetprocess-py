"""Tests for UsersResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import User
from targetprocess.resources.users import UsersResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_users_resource_entity_type():
    """Test UsersResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = UsersResource(mock_client, mock_request_handler)

    assert resource.entity_type == "User"
    assert resource.model_class == User


@pytest.mark.asyncio
async def test_users_inherits_crud():
    """Test UsersResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = UsersResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
