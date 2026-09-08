"""Tests for TestCasesResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.models import TestCase
from targetprocess.resources.test_cases import TestCasesResource
from targetprocess.types import ClientMode


@pytest.mark.asyncio
async def test_test_cases_resource_entity_type():
    """Test TestCasesResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = TestCasesResource(mock_client, mock_request_handler)

    assert resource.entity_type == "TestCase"
    assert resource.model_class == TestCase


@pytest.mark.asyncio
async def test_test_cases_inherits_crud():
    """Test TestCasesResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = TestCasesResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")
