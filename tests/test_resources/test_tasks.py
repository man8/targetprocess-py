"""Tests for TasksResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import Task
from targetprocess.resources.tasks import TasksResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_tasks_resource_entity_type():
    """Test TasksResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = TasksResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Task"
    assert resource.model_class == Task


@pytest.mark.asyncio
async def test_tasks_inherits_crud():
    """Test TasksResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = TasksResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
