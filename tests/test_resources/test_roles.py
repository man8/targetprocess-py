"""Tests for RolesResource."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import Mock

import pytest

from targetprocess.client import TargetProcessClient
from targetprocess.exceptions import AmbiguousMatchError, NotFoundError, ReadOnlyViolation
from targetprocess.models import Role
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.roles import RolesResource
from targetprocess.types import ClientMode

ROLES: list[dict[str, Any]] = [
    {"ResourceType": "Role", "Id": 1, "Name": "Developer"},
    {"ResourceType": "Role", "Id": 2, "Name": "QA Engineer"},
]


def _resource(items: list[dict[str, Any]]) -> tuple[RolesResource, dict[str, Any]]:
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
    return RolesResource(client, handler), seen


@pytest.mark.asyncio
async def test_resource_entity_type_and_model():
    resource, _ = _resource([])

    assert resource.entity_type == "Role"
    assert resource.model_class == Role


@pytest.mark.asyncio
async def test_resolve_returns_the_single_match():
    resource, seen = _resource(ROLES)

    role = await resource.resolve("Developer")

    assert seen["entity_type"] == "Role"
    assert role.id == 1
    assert role.name == "Developer"


@pytest.mark.asyncio
async def test_resolve_is_case_insensitive():
    resource, _ = _resource(ROLES)

    role = await resource.resolve("developer")

    assert role.id == 1


@pytest.mark.asyncio
async def test_resolve_lists_the_valid_names_when_absent():
    resource, _ = _resource(ROLES)

    with pytest.raises(NotFoundError) as excinfo:
        await resource.resolve("Scrum Master")

    message = str(excinfo.value)
    assert "Scrum Master" in message
    assert "Developer" in message
    assert "QA Engineer" in message


@pytest.mark.asyncio
async def test_resolve_refuses_to_guess_between_duplicates():
    duplicates = [ROLES[0], {**ROLES[0], "Id": 99}]
    resource, _ = _resource(duplicates)

    with pytest.raises(AmbiguousMatchError) as excinfo:
        await resource.resolve("Developer")

    assert "Ids: 1, 99" in str(excinfo.value)


@pytest.mark.asyncio
async def test_roles_writes_blocked_in_readonly_mode():
    """Test the full write path raises ReadOnlyViolation on a READONLY client."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(ReadOnlyViolation):
        await client.roles.create(Name="Reviewer")
    with pytest.raises(ReadOnlyViolation):
        await client.roles.update(123, Name="Reviewer")
    with pytest.raises(ReadOnlyViolation):
        await client.roles.delete(123)
