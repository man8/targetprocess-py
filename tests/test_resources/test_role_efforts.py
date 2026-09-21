"""Tests for RoleEffortsResource, and for the derived-roll-up write refusal it is the route for."""

import json
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from targetprocess_py import ClientMode, ReadOnlyViolation, TargetProcessClient, resources
from targetprocess_py.models import RoleEffort
from targetprocess_py.request_handler import RequestHandler
from targetprocess_py.resources.base import BaseResource
from targetprocess_py.resources.bugs import BugsResource
from targetprocess_py.resources.epics import EpicsResource
from targetprocess_py.resources.features import FeaturesResource
from targetprocess_py.resources.requests import RequestsResource
from targetprocess_py.resources.role_efforts import RoleEffortsResource
from targetprocess_py.resources.tasks import TasksResource
from targetprocess_py.resources.user_stories import UserStoriesResource


@pytest.mark.asyncio
async def test_role_efforts_resource_entity_type():
    """Test RoleEffortsResource has correct entity_type."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = RoleEffortsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "RoleEffort"
    assert resource.model_class == RoleEffort


@pytest.mark.asyncio
async def test_role_efforts_update_parses_role_effort():
    """Test update() delegates to the handler and parses a RoleEffort."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.update.return_value = {
        "Id": 456100,
        "ResourceType": "RoleEffort",
        "EffortToDo": 4.0,
        "Role": {"Id": 20, "Name": "Developer"},
        "Assignable": {"Id": 51383, "Name": "Story B"},
    }

    resource = RoleEffortsResource(mock_client, mock_request_handler)

    result = await resource.update(456100, EffortToDo=4.0)

    assert isinstance(result, RoleEffort)
    assert result.id == 456100
    assert result.effort_todo == 4.0
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.update.assert_called_once_with("RoleEffort", 456100, {"EffortToDo": 4.0})


@pytest.mark.asyncio
async def test_role_efforts_writes_blocked_in_readonly_mode():
    """Test the full write path raises ReadOnlyViolation on a READONLY client."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(ReadOnlyViolation):
        await client.role_efforts.create(Assignable={"Id": 1}, Role={"Id": 2})
    with pytest.raises(ReadOnlyViolation):
        await client.role_efforts.update(123, EffortToDo=1.0)
    with pytest.raises(ReadOnlyViolation):
        await client.role_efforts.delete(123)


# --- the derived-roll-up write refusal ---------------------------------------------------------
#
# An Assignable's Effort is the sum of its RoleEfforts, so the work-item
# managers refuse a direct write to it and name this collection as the route.
# The refusal is tested here rather than beside the verified writes because the
# route it names is this resource: a change that moved the route would have to
# change these tests. Names added with the refusal are imported inside each
# test, so that against a library without it each test fails on its own
# assertion rather than at collection.

GUARDED_FIELDS = ("Effort", "EffortCompleted", "EffortToDo")

# Each assignable manager, with the collection (plural) name TP addresses it by.
ASSIGNABLE_COLLECTIONS: dict[type, str] = {
    UserStoriesResource: "UserStories",
    BugsResource: "Bugs",
    TasksResource: "Tasks",
    FeaturesResource: "Features",
    EpicsResource: "Epics",
    RequestsResource: "Requests",
}

# The Assignable-derived collections with no typed manager, so reachable only
# through the generic accessor.
UNTYPED_ASSIGNABLE_COLLECTIONS = (
    "Assignable",
    "PortfolioEpic",
    "TestPlanRun",
    "InboundAssignable",
    "OutboundAssignable",
)


def _client_that_must_not_send() -> tuple[TargetProcessClient, list[httpx.Request]]:
    """A READWRITE client whose transport fails the test if it is ever reached.

    READWRITE deliberately: the refusal sits after the mode and server-capability
    gates, so a READONLY client would raise ``ReadOnlyViolation`` first and prove
    nothing about this guard.
    """
    sent: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        raise AssertionError("a derived-field write reached the transport")

    client = TargetProcessClient(
        domain="example.tpondemand.com", token="test-token", mode=ClientMode.READWRITE
    )
    client._transport._client._transport = httpx.MockTransport(record)
    return client, sent


def _client_that_echoes(body: dict[str, Any]) -> tuple[TargetProcessClient, list[httpx.Request]]:
    """A READWRITE client whose transport answers every request with ``body``."""
    sent: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=body)

    client = TargetProcessClient(
        domain="example.tpondemand.com", token="test-token", mode=ClientMode.READWRITE
    )
    client._transport._client._transport = httpx.MockTransport(respond)
    return client, sent


@pytest.mark.asyncio
@pytest.mark.parametrize("field", GUARDED_FIELDS)
async def test_create_naming_a_derived_roll_up_is_refused_before_any_request(field: str) -> None:
    """A create naming one of the roll-ups never reaches the transport."""
    client, sent = _client_that_must_not_send()

    with pytest.raises(ValueError, match="client.role_efforts") as caught:
        await client.user_stories.create(Name="Story", **{field: 3.0})

    assert f"{field} is not writable on UserStory" in str(caught.value)
    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("field", GUARDED_FIELDS)
async def test_update_naming_a_derived_roll_up_is_refused_before_any_request(field: str) -> None:
    """An update naming one of the roll-ups never reaches the transport."""
    client, sent = _client_that_must_not_send()

    with pytest.raises(ValueError, match="client.role_efforts") as caught:
        await client.user_stories.update(123, **{field: 3.0})

    assert f"{field} is not writable on UserStory" in str(caught.value)
    assert sent == []


@pytest.mark.asyncio
async def test_the_refusal_names_the_role_effort_route_and_the_escape() -> None:
    """The message says why, how to set the value properly, and how to override."""
    client, _ = _client_that_must_not_send()

    with pytest.raises(ValueError) as caught:
        await client.user_stories.update(123, Effort=3.0)

    message = str(caught.value)
    assert "derives Effort from the entity's RoleEfforts" in message
    assert 'client.role_efforts.list(where="Assignable.Id eq <id>", include=["Role"])' in message
    assert "client.role_efforts.update" in message
    assert "client.role_efforts.create" in message
    assert "allow_derived=True" in message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("accessor", "entity_type"),
    [
        ("user_stories", "UserStory"),
        ("bugs", "Bug"),
        ("tasks", "Task"),
        ("features", "Feature"),
        ("epics", "Epic"),
        ("requests", "Request"),
    ],
)
async def test_every_assignable_manager_refuses_the_write(accessor: str, entity_type: str) -> None:
    """The refusal is on the shared base, so all six work-item managers carry it."""
    client, sent = _client_that_must_not_send()

    with pytest.raises(ValueError, match="client.role_efforts") as caught:
        await getattr(client, accessor).update(123, Effort=3.0)

    assert f"not writable on {entity_type}" in str(caught.value)
    assert sent == []


@pytest.mark.asyncio
async def test_the_bulk_paths_refuse_and_name_the_offending_item() -> None:
    """create_many and update_many report the item's position, as their Id guards do."""
    client, sent = _client_that_must_not_send()

    with pytest.raises(ValueError, match=r"create_many item 1: Effort is not writable"):
        await client.tasks.create_many([{"Name": "One"}, {"Name": "Two", "Effort": 2.0}])
    with pytest.raises(ValueError, match=r"update_many item 0: Effort is not writable"):
        await client.tasks.update_many([{"Id": 5, "Effort": 2.0}, {"Id": 6, "Name": "Two"}])

    assert sent == []


@pytest.mark.asyncio
async def test_the_generic_path_refuses_the_same_write() -> None:
    """The generic accessor is not a way round the typed guard, on any of its four writes."""
    client, sent = _client_that_must_not_send()

    with pytest.raises(ValueError, match="client.role_efforts"):
        await client.entities.create("UserStory", Name="Story", Effort=3.0)
    with pytest.raises(ValueError, match="client.role_efforts"):
        await client.entities.update("UserStory", 123, Effort=3.0)
    with pytest.raises(ValueError, match=r"create_many item 0: Effort is not writable"):
        await client.entities.create_many("Bugs", [{"Name": "Bug", "Effort": 1.0}])
    with pytest.raises(ValueError, match=r"update_many item 0: Effort is not writable"):
        await client.entities.update_many("Bugs", [{"Id": 5, "Effort": 1.0}])

    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", UNTYPED_ASSIGNABLE_COLLECTIONS)
async def test_the_generic_path_refuses_on_an_untyped_assignable_collection(
    collection: str,
) -> None:
    """An Assignable-derived collection with no typed manager is covered too."""
    client, sent = _client_that_must_not_send()

    with pytest.raises(ValueError, match="client.role_efforts") as caught:
        await client.entities.update(collection, 123, Effort=3.0)

    assert f"not writable on {collection}" in str(caught.value)
    assert sent == []


@pytest.mark.asyncio
async def test_a_role_effort_write_still_passes() -> None:
    """The route the refusal names is itself unguarded - this is where effort is stored."""
    from targetprocess_py.resources.role_efforts import RoleEffortsResource as Guarded

    assert Guarded.derived_fields == {}

    client, sent = _client_that_echoes(
        {"Id": 456100, "ResourceType": "RoleEffort", "Effort": 3.0, "EffortToDo": 1.0}
    )

    created = await client.role_efforts.create(
        Assignable={"Id": 123}, Role={"Id": 20}, Effort=3.0, EffortToDo=1.0
    )
    updated = await client.role_efforts.update(456100, Effort=3.0, EffortCompleted=2.0)

    assert created.effort == 3.0
    assert updated.effort == 3.0
    assert [json.loads(request.content) for request in sent] == [
        {"Assignable": {"Id": 123}, "Role": {"Id": 20}, "Effort": 3.0, "EffortToDo": 1.0},
        {"Effort": 3.0, "EffortCompleted": 2.0},
    ]


@pytest.mark.asyncio
async def test_allow_derived_sends_the_write_on_every_path() -> None:
    """The escape hatch is what the library's own recorded write fixtures use."""
    client, sent = _client_that_echoes({"Id": 123, "ResourceType": "UserStory", "Effort": 3.0})

    story = await client.user_stories.update(123, Effort=3.0, allow_derived=True)
    await client.user_stories.create(Name="Story", Effort=3.0, allow_derived=True)
    await client.entities.update("UserStory", 123, Effort=3.0, allow_derived=True)

    assert story.effort == 3.0
    assert [json.loads(request.content) for request in sent] == [
        {"Effort": 3.0},
        {"Name": "Story", "Effort": 3.0},
        {"Effort": 3.0},
    ]


@pytest.mark.asyncio
async def test_allow_derived_sends_a_bulk_batch() -> None:
    """The bulk pair take the same escape hatch, typed and generic alike."""
    client, sent = _client_that_echoes(
        {"Items": [{"Id": 5, "ResourceType": "Task", "Effort": 2.0}]}
    )

    await client.tasks.update_many([{"Id": 5, "Effort": 2.0}], allow_derived=True)
    await client.tasks.create_many([{"Name": "One", "Effort": 2.0}], allow_derived=True)
    await client.entities.update_many("Tasks", [{"Id": 5, "Effort": 2.0}], allow_derived=True)

    assert [json.loads(request.content) for request in sent] == [
        [{"Id": 5, "Effort": 2.0}],
        [{"Name": "One", "Effort": 2.0}],
        [{"Id": 5, "Effort": 2.0}],
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("spelling", ["effort", "EFFORT", " Effort ", "eFfOrTtOdO"])
async def test_the_refusal_matches_the_field_in_any_casing_or_padding(spelling: str) -> None:
    """Key matching follows the verification comparison's: case-folded and stripped."""
    client, sent = _client_that_must_not_send()

    with pytest.raises(ValueError, match="client.role_efforts"):
        await client.user_stories.update(123, **{spelling: 3.0})

    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["Progress", "TimeSpent", "TimeRemain", "Name"])
async def test_a_field_outside_the_declared_set_is_sent(field: str) -> None:
    """Only the declared roll-ups are refused; TP's other computed numbers are not.

    Each of these is computed by TP too, and none is declared: a refusal needs
    its own route named in its own message and the same live evidence the
    ignored-filter set is extended on. Pinned so the set cannot widen silently.
    """
    client, sent = _client_that_echoes({"Id": 123, "ResourceType": "UserStory"})

    await client.user_stories.update(123, **{field: 1.0})

    assert [json.loads(request.content) for request in sent] == [{field: 1.0}]


def test_the_guarded_set_is_declared_once_and_shared() -> None:
    """The six managers reference one declaration, whose entries are the three roll-ups."""
    from targetprocess_py.resources._derived import ASSIGNABLE_DERIVED_FIELDS

    assert set(ASSIGNABLE_DERIVED_FIELDS) == set(GUARDED_FIELDS)
    for field, reason in ASSIGNABLE_DERIVED_FIELDS.items():
        assert f"derives {field} from the entity's RoleEfforts" in reason
        assert "client.role_efforts" in reason
    for resource_cls in ASSIGNABLE_COLLECTIONS:
        assert resource_cls.derived_fields is ASSIGNABLE_DERIVED_FIELDS, resource_cls


def test_every_manager_with_derived_fields_is_mirrored_on_the_generic_path() -> None:
    """The generic map reaches each declaring manager, and each untyped collection.

    The counterpart of the ignored-filter walk: a manager that declares a
    derived-field set and is not reachable through the generic accessor's map
    would leave that accessor as the way round its own guard.
    """
    from targetprocess_py.resources._derived import ASSIGNABLE_DERIVED_FIELDS
    from targetprocess_py.resources.assignables import AssignableResource
    from targetprocess_py.resources.entities import (
        _DERIVED_FIELDS,
        _UNTYPED_ASSIGNABLE_COLLECTIONS,
        _spellings,
    )

    # AssignableResource declares the set once for the six managers; it is their
    # base class rather than a manager, so it has no collection to mirror.
    declaring = {
        candidate
        for candidate in (getattr(resources, name) for name in resources.__all__)
        if isinstance(candidate, type)
        and issubclass(candidate, BaseResource)
        and candidate is not AssignableResource
        and candidate.derived_fields
    }
    assert declaring == set(ASSIGNABLE_COLLECTIONS)

    for resource_cls, collection in ASSIGNABLE_COLLECTIONS.items():
        for spelling in {*_spellings(resource_cls.entity_type), collection, collection.upper()}:
            assert _DERIVED_FIELDS.get(spelling.casefold()) is resource_cls.derived_fields, spelling
    # The untyped collections this suite names are exactly the ones the module
    # declares, so the two cannot drift apart unnoticed.
    assert set(_UNTYPED_ASSIGNABLE_COLLECTIONS) == set(UNTYPED_ASSIGNABLE_COLLECTIONS)

    for singular in UNTYPED_ASSIGNABLE_COLLECTIONS:
        for spelling in {*_spellings(singular), singular.upper()}:
            assert _DERIVED_FIELDS.get(spelling.casefold()) is ASSIGNABLE_DERIVED_FIELDS, spelling

    declared_spellings = frozenset().union(
        *(_spellings(cls.entity_type) for cls in ASSIGNABLE_COLLECTIONS),
        *(_spellings(singular) for singular in UNTYPED_ASSIGNABLE_COLLECTIONS),
    )
    assert set(_DERIVED_FIELDS) <= declared_spellings


def test_the_model_and_the_resource_both_state_that_effort_is_derived() -> None:
    """The docstrings a reader meets first say where effort is stored."""
    from targetprocess_py.models import AssignableEntity
    from targetprocess_py.resources.role_efforts import RoleEffortsResource as Documented

    model_doc = AssignableEntity.__doc__ or ""
    assert "derived" in model_doc
    assert "RoleEffort" in model_doc
    resource_doc = Documented.__doc__ or ""
    assert "derived" in resource_doc
    assert "sum" in resource_doc
