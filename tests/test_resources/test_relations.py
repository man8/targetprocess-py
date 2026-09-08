"""Tests for RelationsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import ClientMode, ReadOnlyViolation, TargetProcessClient
from targetprocess.models import Relation
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.relations import RelationsResource


@pytest.mark.asyncio
async def test_relations_resource_entity_type():
    """Test RelationsResource has correct entity_type."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = RelationsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Relation"
    assert resource.model_class == Relation


@pytest.mark.asyncio
async def test_relations_inherits_crud():
    """Test RelationsResource inherits CRUD operations."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = RelationsResource(mock_client, mock_request_handler)

    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")


@pytest.mark.asyncio
async def test_relations_create_parses_relation():
    """Test create() delegates to the handler and parses a Relation."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.create.return_value = {
        "Id": 53,
        "ResourceType": "Relation",
        "Master": {"Id": 456, "Name": "Blocking story"},
        "Slave": {"Id": 123, "Name": "Blocked story"},
        "RelationType": {"Id": 2, "Name": "Blocker"},
    }

    resource = RelationsResource(mock_client, mock_request_handler)

    # Reference data from one production instance (Blocker is Id 2 there);
    # ids are instance-specific, so real callers resolve them by name. The
    # Master is the blocking item.
    result = await resource.create(Master={"Id": 456}, Slave={"Id": 123}, RelationType={"Id": 2})

    assert isinstance(result, Relation)
    assert result.id == 53
    assert result.master is not None and result.master.id == 456
    assert result.slave is not None and result.slave.id == 123
    assert result.relation_type is not None and result.relation_type.name == "Blocker"
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.create.assert_called_once_with(
        "Relation",
        {"Master": {"Id": 456}, "Slave": {"Id": 123}, "RelationType": {"Id": 2}},
    )


@pytest.mark.asyncio
async def test_relations_writes_blocked_in_readonly_mode():
    """Test the full write path raises ReadOnlyViolation on a READONLY client."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(ReadOnlyViolation):
        await client.relations.create(Master={"Id": 1}, Slave={"Id": 2}, RelationType={"Id": 3})
    with pytest.raises(ReadOnlyViolation):
        await client.relations.update(123, RelationType={"Id": 5})
    with pytest.raises(ReadOnlyViolation):
        await client.relations.delete(123)
