"""Tests for RelationTypesResource."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.client import TargetProcessClient
from targetprocess.exceptions import AmbiguousMatchError, NotFoundError, ReadOnlyViolation
from targetprocess.models import RelationType
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.relation_types import RelationTypesResource
from targetprocess.types import ClientMode

# Reference data from one production instance (Dependency 1, Blocker 2,
# Relation 3, Link 4, Duplicate 5 there). Ids are instance-specific, which is
# exactly why resolve() exists.
RELATION_TYPES: list[dict[str, Any]] = [
    {"ResourceType": "RelationType", "Id": 2, "Name": "Blocker"},
    {"ResourceType": "RelationType", "Id": 3, "Name": "Relation"},
    {"ResourceType": "RelationType", "Id": 5, "Name": "Duplicate"},
]


def _resource(items: list[dict[str, Any]]) -> tuple[RelationTypesResource, dict[str, Any]]:
    """Build a resource whose handler yields `items` and records its kwargs."""
    seen: dict[str, Any] = {}

    async def _list(entity_type: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        seen["entity_type"] = entity_type
        seen.update(kwargs)
        for item in items:
            yield item

    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READONLY
    handler = Mock(spec=RequestHandler)
    handler.list = _list
    return RelationTypesResource(client, handler), seen


@pytest.mark.asyncio
async def test_resource_entity_type_and_model():
    resource, _ = _resource([])

    assert resource.entity_type == "RelationType"
    assert resource.model_class == RelationType


@pytest.mark.asyncio
async def test_resolve_returns_the_single_match():
    resource, seen = _resource(RELATION_TYPES)

    relation_type = await resource.resolve("Blocker")

    assert seen["entity_type"] == "RelationType"
    assert relation_type.id == 2
    assert relation_type.name == "Blocker"


@pytest.mark.asyncio
async def test_resolve_is_case_insensitive():
    resource, _ = _resource(RELATION_TYPES)

    relation_type = await resource.resolve("blocker")

    assert relation_type.id == 2


@pytest.mark.asyncio
async def test_resolve_lists_the_valid_names_when_absent():
    resource, _ = _resource(RELATION_TYPES)

    with pytest.raises(NotFoundError) as excinfo:
        await resource.resolve("Dependency")

    message = str(excinfo.value)
    assert "Dependency" in message
    assert "Blocker" in message
    assert "Duplicate" in message


@pytest.mark.asyncio
async def test_resolve_refuses_to_guess_between_duplicates():
    duplicates = [RELATION_TYPES[0], {**RELATION_TYPES[0], "Id": 99}]
    resource, _ = _resource(duplicates)

    with pytest.raises(AmbiguousMatchError) as excinfo:
        await resource.resolve("Blocker")

    assert "Ids: 2, 99" in str(excinfo.value)


@pytest.mark.asyncio
async def test_relation_types_writes_blocked_in_readonly_mode():
    """Test the full write path raises ReadOnlyViolation on a READONLY client."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(ReadOnlyViolation):
        await client.relation_types.create(Name="Escalates")
    with pytest.raises(ReadOnlyViolation):
        await client.relation_types.update(123, Name="Escalates")
    with pytest.raises(ReadOnlyViolation):
        await client.relation_types.delete(123)


@pytest.mark.asyncio
async def test_relation_types_create_refused_in_readwrite_mode():
    """Server-side read-only: create raises even in READWRITE mode, pre-request."""
    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READWRITE
    handler = AsyncMock(spec=RequestHandler)
    resource = RelationTypesResource(client, handler)

    with pytest.raises(ReadOnlyViolation) as excinfo:
        await resource.create(Name="Escalates")

    assert "read-only on the server" in str(excinfo.value)
    handler.create.assert_not_called()
    # The refusal precedes the mode gate entirely - mode never comes into it.
    client._check_write_permission.assert_not_called()


@pytest.mark.asyncio
async def test_relation_types_update_refused_in_readwrite_mode():
    """Server-side read-only: update raises even in READWRITE mode, pre-request."""
    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READWRITE
    handler = AsyncMock(spec=RequestHandler)
    resource = RelationTypesResource(client, handler)

    with pytest.raises(ReadOnlyViolation):
        await resource.update(123, Name="Escalates")

    handler.update.assert_not_called()
    client._check_write_permission.assert_not_called()


@pytest.mark.asyncio
async def test_relation_types_delete_refused_in_readwrite_mode():
    """Server-side read-only: delete raises even in READWRITE mode, pre-request."""
    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READWRITE
    handler = AsyncMock(spec=RequestHandler)
    resource = RelationTypesResource(client, handler)

    with pytest.raises(ReadOnlyViolation):
        await resource.delete(123)

    handler.delete.assert_not_called()
    client._check_write_permission.assert_not_called()
