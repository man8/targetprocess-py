"""Tests for CommentsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import ClientMode, ReadOnlyViolation, RequestHandler, TargetProcessClient
from targetprocess.models import Comment
from targetprocess.resources.comments import CommentsResource


@pytest.mark.asyncio
async def test_comments_resource_entity_type():
    """Test CommentsResource has correct entity_type."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = CommentsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Comment"
    assert resource.model_class == Comment


@pytest.mark.asyncio
async def test_comments_inherits_crud():
    """Test CommentsResource inherits CRUD operations."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = CommentsResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")


@pytest.mark.asyncio
async def test_comments_create_parses_comment():
    """Test create() delegates to the handler and parses a Comment."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client._check_write_permission = Mock(spec=TargetProcessClient._check_write_permission)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.create.return_value = {
        "Id": 111213,
        "ResourceType": "Comment",
        "Description": "posted body",
        "General": {"Id": 74270, "Name": "Story A"},
    }

    resource = CommentsResource(mock_client, mock_request_handler)

    result = await resource.create(Description="posted body", General={"Id": 74270})

    assert isinstance(result, Comment)
    assert result.id == 111213
    assert result.description == "posted body"
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.create.assert_called_once_with(
        "Comment", {"Description": "posted body", "General": {"Id": 74270}}
    )


@pytest.mark.asyncio
async def test_comments_writes_blocked_in_readonly_mode():
    """Test the full write path raises ReadOnlyViolation on a READONLY client."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(ReadOnlyViolation):
        await client.comments.create(Description="x", General={"Id": 1})
    with pytest.raises(ReadOnlyViolation):
        await client.comments.update(123, Description="y")
    with pytest.raises(ReadOnlyViolation):
        await client.comments.delete(123)
