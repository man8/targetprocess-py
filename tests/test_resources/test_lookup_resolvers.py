"""Tests for the name resolvers on the lookup resources.

Severities, Processes, EntityTypes and CustomActivities each expose
``resolve(name)`` over the shared ``_resolve_by_name`` body (see
test_base_resource.py for that helper's own contract). Parametrised so the
four resolvers are pinned to one behaviour rather than four copies of it.
"""

from typing import Any
from unittest.mock import Mock

import pytest

from targetprocess.client import TargetProcessClient
from targetprocess.exceptions import AmbiguousMatchError, NotFoundError
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.base import BaseResource
from targetprocess.resources.custom_activities import CustomActivitiesResource
from targetprocess.resources.entity_types import EntityTypesResource
from targetprocess.resources.processes import ProcessesResource
from targetprocess.resources.severities import SeveritiesResource
from targetprocess.types import ClientMode
from tests._support.request_handler import scripted_list

# (resource class, wire entity type, noun in messages, two sample names)
RESOLVERS = [
    pytest.param(
        SeveritiesResource, "Severity", "severity", ("Blocking", "Small"), id="severities"
    ),
    pytest.param(ProcessesResource, "Process", "process", ("Scrum", "Kanban"), id="processes"),
    pytest.param(
        EntityTypesResource, "EntityType", "entity type", ("UserStory", "Bug"), id="entity_types"
    ),
    pytest.param(
        CustomActivitiesResource,
        "CustomActivity",
        "custom activity",
        ("Meetings", "Support"),
        id="custom_activities",
    ),
]


def _resource(
    resource_cls: type[BaseResource[Any]], entity_type: str, records: list[dict[str, Any]]
) -> tuple[Any, dict[str, Any]]:
    """Build a resource whose handler yields ``records`` and records its arguments."""
    _list, seen = scripted_list([{"ResourceType": entity_type, **record} for record in records])
    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READONLY
    handler = Mock(spec=RequestHandler)
    handler.list = _list
    return resource_cls(client, handler), seen


@pytest.mark.asyncio
@pytest.mark.parametrize(("resource_cls", "entity_type", "what", "names"), RESOLVERS)
async def test_resolve_returns_the_single_match(resource_cls, entity_type, what, names):
    first, second = names
    resource, seen = _resource(
        resource_cls, entity_type, [{"Id": 1, "Name": first}, {"Id": 2, "Name": second}]
    )

    match = await resource.resolve(second)

    assert seen["entity_type"] == entity_type
    assert match.id == 2
    assert match.name == second


@pytest.mark.asyncio
@pytest.mark.parametrize(("resource_cls", "entity_type", "what", "names"), RESOLVERS)
async def test_resolve_is_case_insensitive(resource_cls, entity_type, what, names):
    first, _ = names
    resource, _ = _resource(resource_cls, entity_type, [{"Id": 1, "Name": first}])

    match = await resource.resolve(first.swapcase())

    assert match.id == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("resource_cls", "entity_type", "what", "names"), RESOLVERS)
async def test_resolve_lists_the_valid_names_when_absent(resource_cls, entity_type, what, names):
    first, second = names
    resource, _ = _resource(
        resource_cls, entity_type, [{"Id": 1, "Name": first}, {"Id": 2, "Name": second}]
    )

    with pytest.raises(NotFoundError) as excinfo:
        await resource.resolve("No Such Thing")

    message = str(excinfo.value)
    assert message.startswith(f"no {what} named 'No Such Thing'")
    assert first in message and second in message


@pytest.mark.asyncio
@pytest.mark.parametrize(("resource_cls", "entity_type", "what", "names"), RESOLVERS)
async def test_resolve_refuses_to_guess_between_duplicates(resource_cls, entity_type, what, names):
    first, _ = names
    resource, _ = _resource(
        resource_cls, entity_type, [{"Id": 1, "Name": first}, {"Id": 99, "Name": first}]
    )

    with pytest.raises(AmbiguousMatchError) as excinfo:
        await resource.resolve(first)

    assert str(excinfo.value) == f"{what} {first!r} matched 2 records (Ids: 1, 99)"
