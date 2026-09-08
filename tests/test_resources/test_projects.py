"""Tests for ProjectsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import Project
from targetprocess.resources.projects import ProjectsResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_projects_resource_entity_type():
    """Test ProjectsResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = ProjectsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Project"
    assert resource.model_class == Project


@pytest.mark.asyncio
async def test_projects_inherits_crud():
    """Test ProjectsResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = ProjectsResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
