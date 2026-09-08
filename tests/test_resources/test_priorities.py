"""Tests for PrioritiesResource."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import Mock

import pytest

from targetprocess.client import TargetProcessClient
from targetprocess.exceptions import AmbiguousMatchError, NotFoundError
from targetprocess.models import Priority
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.priorities import PrioritiesResource
from targetprocess.types import ClientMode

USER_STORY_PRIORITIES: list[dict[str, Any]] = [
    {
        "ResourceType": "Priority",
        "Id": 1,
        "Name": "Must Have",
        "Importance": 1,
        "IsDefault": False,
        "EntityType": {"ResourceType": "EntityType", "Id": 4, "Name": "UserStory"},
    },
    {
        "ResourceType": "Priority",
        "Id": 2,
        "Name": "Great",
        "Importance": 2,
        "IsDefault": False,
        "EntityType": {"ResourceType": "EntityType", "Id": 4, "Name": "UserStory"},
    },
]


def _resource(items: list[dict[str, Any]]) -> tuple[PrioritiesResource, dict[str, Any]]:
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
    return PrioritiesResource(client, handler), seen


@pytest.mark.asyncio
async def test_resource_entity_type_and_model():
    resource, _ = _resource([])

    assert resource.entity_type == "Priority"
    assert resource.model_class == Priority


@pytest.mark.asyncio
async def test_for_entity_type_filters_on_entity_type_name():
    resource, seen = _resource(USER_STORY_PRIORITIES)

    priorities = await resource.for_entity_type("UserStory")

    assert seen["entity_type"] == "Priority"
    assert seen["where"] == "EntityType.Name eq 'UserStory'"
    assert seen.get("limit") is None
    assert [p.id for p in priorities] == [1, 2]


@pytest.mark.asyncio
async def test_for_entity_type_rejects_a_non_identifier():
    resource, _ = _resource(USER_STORY_PRIORITIES)

    with pytest.raises(ValueError, match="entity_type must be a TP entity type name"):
        await resource.for_entity_type("User'Story")


@pytest.mark.asyncio
async def test_for_entity_type_rejects_the_empty_string():
    resource, _ = _resource(USER_STORY_PRIORITIES)

    with pytest.raises(ValueError, match="entity_type must be a TP entity type name"):
        await resource.for_entity_type("")


@pytest.mark.asyncio
async def test_resolve_returns_the_single_match():
    resource, _ = _resource(USER_STORY_PRIORITIES)

    priority = await resource.resolve("Must Have", entity_type="UserStory")

    assert priority.id == 1
    assert priority.name == "Must Have"


@pytest.mark.asyncio
async def test_resolve_is_case_insensitive():
    resource, _ = _resource(USER_STORY_PRIORITIES)

    priority = await resource.resolve("must have", entity_type="UserStory")

    assert priority.id == 1


@pytest.mark.asyncio
async def test_resolve_lists_the_valid_names_when_absent():
    resource, _ = _resource(USER_STORY_PRIORITIES)

    with pytest.raises(NotFoundError) as excinfo:
        await resource.resolve("Fix ASAP", entity_type="UserStory")

    message = str(excinfo.value)
    assert "Fix ASAP" in message
    assert "Must Have" in message
    assert "Great" in message


@pytest.mark.asyncio
async def test_resolve_refuses_to_guess_between_duplicates():
    duplicates = [
        USER_STORY_PRIORITIES[0],
        {**USER_STORY_PRIORITIES[0], "Id": 99},
    ]
    resource, _ = _resource(duplicates)

    with pytest.raises(AmbiguousMatchError) as excinfo:
        await resource.resolve("Must Have", entity_type="UserStory")

    message = str(excinfo.value)
    assert "Ids: 1, 99" in message


@pytest.mark.asyncio
async def test_resolve_rejects_a_non_identifier_entity_type():
    resource, _ = _resource(USER_STORY_PRIORITIES)

    with pytest.raises(ValueError, match="entity_type must be a TP entity type name"):
        await resource.resolve("x", entity_type="User'Story")


@pytest.mark.asyncio
async def test_client_exposes_priorities_lazily():
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="t", mode=ClientMode.READONLY
    )
    try:
        first = client.priorities
        assert isinstance(first, PrioritiesResource)
        assert client.priorities is first
    finally:
        await client.aclose()
