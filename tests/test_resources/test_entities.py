"""Tests for EntitiesResource (generic CRUD for any entity type)."""

from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from targetprocess import resources
from targetprocess.client import TargetProcessClient
from targetprocess.exceptions import ReadOnlyViolation
from targetprocess.models import Bug, NamedEntity, UserStory
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.base import BaseResource
from targetprocess.resources.custom_rules import CustomRulesResource
from targetprocess.resources.entities import (
    _SERVER_GUARDED_RESOURCES,
    _UNHYDRATABLE_RESOURCES,
    EntitiesResource,
    _spellings,
)
from targetprocess.resources.entity_types import EntityTypesResource
from targetprocess.resources.processes import ProcessesResource
from targetprocess.resources.relation_types import RelationTypesResource
from targetprocess.resources.terms import TermsResource
from targetprocess.types import ClientMode
from tests._support.request_handler import scripted_list


@pytest.mark.asyncio
async def test_entities_get_any_type():
    """Test entities.get() can fetch any entity type."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    # Mock returning a Bug
    expected_bug = Bug(id=123, name="Test Bug", resource_type="Bug")
    mock_request_handler.get.return_value = expected_bug

    resource = EntitiesResource(mock_client, mock_request_handler)

    result = await resource.get("Bug", 123)

    assert result == expected_bug
    mock_request_handler.get.assert_called_once_with(
        "Bug",
        123,
        include=None,
        exclude=None,
        result_include=None,
        append=None,
        innertake=None,
    )


@pytest.mark.asyncio
async def test_entities_list_any_type():
    """Test entities.list() can list any entity type."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    async def mock_list(*args, **kwargs):
        yield UserStory(id=1, name="Story 1", resource_type="UserStory")
        yield UserStory(id=2, name="Story 2", resource_type="UserStory")

    mock_request_handler.list = mock_list

    resource = EntitiesResource(mock_client, mock_request_handler)

    results = [item async for item in resource.list("UserStory", limit=10)]

    assert len(results) == 2
    assert results[0].id == 1


@pytest.mark.asyncio
async def test_entities_create_delegates_and_checks_permission():
    """create() checks write permission and delegates to the generic handler path."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.create.return_value = {
        "ResourceType": "Objective",
        "Id": 5,
        "Name": "Q3 goal",
    }

    resource = EntitiesResource(mock_client, mock_request_handler)

    result = await resource.create("Objective", Name="Q3 goal", Project={"Id": 2})

    assert isinstance(result, NamedEntity)
    assert result.id == 5
    assert result.name == "Q3 goal"
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.create.assert_called_once_with(
        "Objective", {"Name": "Q3 goal", "Project": {"Id": 2}}
    )


@pytest.mark.asyncio
async def test_entities_update_delegates_and_checks_permission():
    """update() checks write permission and delegates to the generic handler path."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.update.return_value = {
        "ResourceType": "Objective",
        "Id": 5,
        "Name": "Renamed",
    }

    resource = EntitiesResource(mock_client, mock_request_handler)

    result = await resource.update("Objective", 5, Name="Renamed")

    assert result.name == "Renamed"
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.update.assert_called_once_with("Objective", 5, {"Name": "Renamed"})


@pytest.mark.asyncio
async def test_entities_delete_delegates_and_checks_permission():
    """delete() checks write permission and delegates to the generic handler path."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.delete.return_value = None

    resource = EntitiesResource(mock_client, mock_request_handler)

    await resource.delete("Objective", 5)

    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.delete.assert_called_once_with("Objective", 5)


@pytest.mark.asyncio
async def test_entities_create_many_delegates_to_bulk():
    """create_many() validates shape, checks permission, and delegates to bulk."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.bulk.return_value = [
        {"ResourceType": "Objective", "Id": 5, "Name": "First"},
        {"ResourceType": "Objective", "Id": 6, "Name": "Second"},
    ]

    resource = EntitiesResource(mock_client, mock_request_handler)

    items = [{"Name": "First"}, {"Name": "Second"}]
    result = await resource.create_many("Objective", items)

    assert [entity.id for entity in result] == [5, 6]
    assert all(isinstance(entity, NamedEntity) for entity in result)
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.bulk.assert_called_once_with("Objective", items)


@pytest.mark.asyncio
async def test_entities_update_many_delegates_to_bulk():
    """update_many() validates shape, checks permission, and delegates to bulk."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.bulk.return_value = [
        {"ResourceType": "Objective", "Id": 5, "Name": "Renamed"},
    ]

    resource = EntitiesResource(mock_client, mock_request_handler)

    items = [{"Id": 5, "Name": "Renamed"}]
    result = await resource.update_many("Objective", items)

    assert [entity.id for entity in result] == [5]
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.bulk.assert_called_once_with("Objective", items)


@pytest.mark.asyncio
async def test_entities_update_many_canonicalises_a_lowercase_id():
    """A lowercase ``id`` is accepted as the Id and sent as ``Id``.

    The bulk endpoint selects update-vs-create by the presence of ``Id``
    exactly; forwarding ``{"id": 7}`` verbatim would create a new entity.
    The generic path canonicalises the key the way BaseResource.update_many
    does.
    """
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.bulk.return_value = [
        {"ResourceType": "Objective", "Id": 7, "Name": "Renamed"},
    ]

    resource = EntitiesResource(mock_client, mock_request_handler)

    result = await resource.update_many("Objective", [{"id": 7, "Name": "Renamed"}])

    assert [entity.id for entity in result] == [7]
    mock_request_handler.bulk.assert_called_once_with("Objective", [{"Id": 7, "Name": "Renamed"}])


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_type", ["Process", "Processes", "processes"])
async def test_entities_mirror_the_typed_include_refusal(entity_type: str):
    """A generic read of a Process with include=CustomFields is refused before the wire.

    The typed manager refuses it because TP serves the definitions
    collection under that key; the generic path parses into the same
    Entity base, so it would hit the same ParseError, and refuses the same
    way instead.
    """
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    resource = EntitiesResource(mock_client, mock_request_handler)

    with pytest.raises(ValueError, match="client.custom_fields"):
        await resource.get(entity_type, 2, include=["CustomFields"])
    with pytest.raises(ValueError, match="client.custom_fields"):
        async for _ in resource.list(entity_type, include=["customfields[Id]"]):
            pass
    mock_request_handler.get.assert_not_called()
    mock_request_handler.list.assert_not_called()


def test_every_resource_with_an_unhydratable_include_is_mirrored_on_the_generic_path():
    """The read-side map covers every exported typed resource that refuses an include."""
    declaring: set[type[BaseResource[Any]]] = set()
    for name in resources.__all__:
        candidate = getattr(resources, name)
        if (
            isinstance(candidate, type)
            and issubclass(candidate, BaseResource)
            and candidate is not BaseResource
            and candidate.unhydratable_includes
        ):
            declaring.add(candidate)

    assert declaring == set(_UNHYDRATABLE_RESOURCES.values()) == {ProcessesResource}
    _assert_reachable_by_every_spelling(_UNHYDRATABLE_RESOURCES, ProcessesResource)


@pytest.mark.parametrize(
    ("entity_type", "expected"),
    [
        ("Process", {"process", "processs", "processes"}),
        ("Severity", {"severity", "severitys", "severityes", "severities"}),
        ("Term", {"term", "terms", "termes"}),
    ],
)
def test_spellings_cover_the_singular_and_the_plural_tp_uses(entity_type: str, expected: set[str]):
    """The derived spellings include the plural TP actually addresses the collection by."""
    assert _spellings(entity_type) == frozenset(expected)


@pytest.mark.asyncio
async def test_entities_bulk_shape_validation():
    """create_many refuses Id-bearing items; update_many refuses Id-less ones."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = EntitiesResource(mock_client, mock_request_handler)

    with pytest.raises(ValueError, match="update_many"):
        await resource.create_many("Objective", [{"Id": 5, "Name": "bad"}])
    with pytest.raises(ValueError, match="create_many"):
        await resource.update_many("Objective", [{"Name": "no id"}])

    mock_request_handler.bulk.assert_not_called()


def _client_that_must_not_send(mode: ClientMode) -> TargetProcessClient:
    """A real client whose transport fails the test if any request is sent.

    The guards under test must refuse before the wire; if one regresses,
    this fails as a clean assertion rather than as a live request off the
    box followed by a network error.
    """
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=mode,
    )

    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"guard did not fire: {request.method} {request.url.path}")

    client._transport._client._transport = httpx.MockTransport(handle)
    return client


@pytest.mark.asyncio
async def test_entities_writes_blocked_in_readonly_mode():
    """The full generic write path raises ReadOnlyViolation on a READONLY client."""
    client = _client_that_must_not_send(ClientMode.READONLY)

    with pytest.raises(ReadOnlyViolation):
        await client.entities.create("Objective", Name="x")
    with pytest.raises(ReadOnlyViolation):
        await client.entities.update("Objective", 5, Name="x")
    with pytest.raises(ReadOnlyViolation):
        await client.entities.delete("Objective", 5)
    with pytest.raises(ReadOnlyViolation):
        await client.entities.create_many("Objective", [{"Name": "x"}])
    with pytest.raises(ReadOnlyViolation):
        await client.entities.update_many("Objective", [{"Id": 5}])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_type",
    [
        "RelationType",
        "RelationTypes",
        "relationtype",
        "RELATIONTYPES",
        "EntityType",
        "EntityTypes",
        "Term",
        "TERMS",
    ],
)
async def test_entities_server_read_only_type_refused_in_any_mode(entity_type: str):
    """A generic write naming a server-read-only collection raises even on READWRITE.

    Mirrors the typed RelationTypesResource / EntityTypesResource /
    TermsResource guards, so the generic path cannot be used to sidestep
    them - any casing, singular or plural.
    """
    client = _client_that_must_not_send(ClientMode.READWRITE)

    with pytest.raises(ReadOnlyViolation, match="read-only on the server"):
        await client.entities.create(entity_type, Name="x")
    with pytest.raises(ReadOnlyViolation, match="read-only on the server"):
        await client.entities.update(entity_type, 5, Name="x")
    with pytest.raises(ReadOnlyViolation, match="read-only on the server"):
        await client.entities.delete(entity_type, 5)
    with pytest.raises(ReadOnlyViolation, match="read-only on the server"):
        await client.entities.create_many(entity_type, [{"Name": "x"}])
    with pytest.raises(ReadOnlyViolation, match="read-only on the server"):
        await client.entities.update_many(entity_type, [{"Id": 5}])


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_type", ["CustomRule", "CustomRules", "customrules"])
async def test_entities_partially_writable_type_refuses_only_the_missing_operations(
    entity_type: str,
):
    """The generic path mirrors a per-operation server restriction, not just the blanket one.

    CustomRules is update-only on the server: create, delete and create_many
    are refused before the wire in READWRITE, while update and update_many
    go through the ordinary gate and reach the handler.
    """
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.update.return_value = {
        "ResourceType": "CustomRule",
        "Id": 7,
        "Name": "Sample rule",
        "IsEnabled": False,
    }
    mock_request_handler.bulk.return_value = [
        {"ResourceType": "CustomRule", "Id": 7, "Name": "Sample rule", "IsEnabled": True}
    ]
    resource = EntitiesResource(mock_client, mock_request_handler)

    with pytest.raises(ReadOnlyViolation, match="does not accept create on the server"):
        await resource.create(entity_type, Name="x")
    with pytest.raises(ReadOnlyViolation, match="does not accept delete on the server"):
        await resource.delete(entity_type, 7)
    with pytest.raises(ReadOnlyViolation, match="does not accept create on the server"):
        await resource.create_many(entity_type, [{"Name": "x"}])
    mock_client._check_write_permission.assert_not_called()

    updated = await resource.update(entity_type, 7, IsEnabled=False)
    assert updated.id == 7
    mock_request_handler.update.assert_called_once_with(entity_type, 7, {"IsEnabled": False})
    batch = await resource.update_many(entity_type, [{"Id": 7, "IsEnabled": True}])
    assert [rule.id for rule in batch] == [7]
    assert mock_client._check_write_permission.call_count == 2


# The TP collection (plural) name of every guarded resource. The generic path
# is addressed by collection name as often as by entity type, so each guard
# map must answer to the plural TP actually uses - ``Processes`` and
# ``Severities`` are not ``entity_type + "s"``. Listing the real plural here
# makes a spelling the map cannot reach a test failure rather than a silent
# gap.
GUARDED_COLLECTION_NAMES: dict[type[BaseResource[Any]], str] = {
    RelationTypesResource: "RelationTypes",
    EntityTypesResource: "EntityTypes",
    TermsResource: "Terms",
    CustomRulesResource: "CustomRules",
    ProcessesResource: "Processes",
}


def _assert_reachable_by_every_spelling(
    guard_map: dict[str, type[BaseResource[Any]]], resource_cls: type[BaseResource[Any]]
) -> None:
    singular, plural = resource_cls.entity_type, GUARDED_COLLECTION_NAMES[resource_cls]
    for spelling in (singular, plural, singular.upper(), plural.lower()):
        assert guard_map.get(spelling.casefold()) is resource_cls, spelling


def test_every_server_restricted_resource_is_mirrored_on_the_generic_path():
    """The guard map covers every exported typed resource with a server-side restriction.

    A typed resource that gains ``server_read_only`` or a ``server_can_*``
    flag without being listed in ``_SERVER_GUARDED_RESOURCES`` would leave
    the generic path a way around its guard; walking the exported resources
    fails that omission here rather than in production. The plural check
    proves the collection spelling reaches the same entry as the singular.
    """
    restricted: set[type[BaseResource[Any]]] = set()
    for name in resources.__all__:
        candidate = getattr(resources, name)
        if (
            isinstance(candidate, type)
            and issubclass(candidate, BaseResource)
            and candidate is not BaseResource
            and not all(candidate.server_permits(op) for op in ("create", "update", "delete"))
        ):
            restricted.add(candidate)

    assert restricted == set(_SERVER_GUARDED_RESOURCES.values())
    assert restricted == set(GUARDED_COLLECTION_NAMES) - {ProcessesResource}
    for resource_cls in restricted:
        _assert_reachable_by_every_spelling(_SERVER_GUARDED_RESOURCES, resource_cls)
    for key, resource_cls in _SERVER_GUARDED_RESOURCES.items():
        assert key in _spellings(resource_cls.entity_type)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_type",
    ["RelationTypes/", " RelationType", "RelationType/bulk/..", "UserStories/57731"],
)
async def test_entities_perturbed_type_name_refused_before_guard_lookup(entity_type: str):
    """A perturbed name is refused as malformed, so it can neither dodge the
    server-read-only mirror nor re-shape the request path.

    ``"UserStories/57731"`` would otherwise turn a create into an update of
    entity 57731; ``"RelationTypes/"`` would otherwise miss the name lookup.
    """
    client = _client_that_must_not_send(ClientMode.READWRITE)
    match = "entity_type must be a TP entity type name"

    with pytest.raises(ValueError, match=match):
        await client.entities.create(entity_type, Name="x")
    with pytest.raises(ValueError, match=match):
        await client.entities.update(entity_type, 5, Name="x")
    with pytest.raises(ValueError, match=match):
        await client.entities.delete(entity_type, 5)
    with pytest.raises(ValueError, match=match):
        await client.entities.create_many(entity_type, [{"Name": "x"}])
    with pytest.raises(ValueError, match=match):
        await client.entities.update_many(entity_type, [{"Id": 5}])


@pytest.mark.asyncio
async def test_entities_get_named_type_parses_raw_payload_with_name():
    """Test generic get() of a named type parses raw wire payload with .name.

    Regression coverage: the generic path must not lose ``.name`` for named
    entity types (Bug, UserStory, ...) when parsing a raw API payload.
    """
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    # Raw wire-shaped payload, as RequestHandler.get actually returns it -
    # not a pre-built model instance.
    mock_request_handler.get.return_value = {
        "ResourceType": "Bug",
        "Id": 9,
        "Name": "crash",
    }

    resource = EntitiesResource(mock_client, mock_request_handler)

    result = await resource.get("Bug", 9)

    assert result.name == "crash"
    assert result.id == 9


@pytest.mark.asyncio
async def test_entities_get_user_shaped_payload_has_no_name():
    """Test generic get() of a User-shaped payload (no Name key) parses name=None."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    # User payloads carry no "Name" key at all.
    mock_request_handler.get.return_value = {
        "ResourceType": "User",
        "Id": 42,
        "FirstName": "Ada",
        "LastName": "Lovelace",
    }

    resource = EntitiesResource(mock_client, mock_request_handler)

    result = await resource.get("User", 42)

    assert result.name is None
    assert result.id == 42


@pytest.mark.asyncio
async def test_entities_list_yields_named_entity_instances():
    """Test generic list() yields NamedEntity instances."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    async def mock_list(*args, **kwargs):
        yield {"ResourceType": "UserStory", "Id": 1, "Name": "Story 1"}
        yield {"ResourceType": "UserStory", "Id": 2, "Name": "Story 2"}

    mock_request_handler.list = mock_list

    resource = EntitiesResource(mock_client, mock_request_handler)

    results = [item async for item in resource.list("UserStory", limit=10)]

    assert len(results) == 2
    assert all(isinstance(item, NamedEntity) for item in results)
    assert results[0].name == "Story 1"


@pytest.mark.asyncio
async def test_entities_get_forwards_shaping_params():
    """Test generic get() forwards the shaping params to RequestHandler."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.get.return_value = {"ResourceType": "Bug", "Id": 9, "Name": "crash"}

    resource = EntitiesResource(mock_client, mock_request_handler)

    result = await resource.get(
        "Bug",
        9,
        include=["Name"],
        exclude=["Description"],
        result_include=["Id"],
        append=["Tasks-Count"],
        innertake=2,
    )

    assert result.id == 9
    mock_request_handler.get.assert_called_once_with(
        "Bug",
        9,
        include=["Name"],
        exclude=["Description"],
        result_include=["Id"],
        append=["Tasks-Count"],
        innertake=2,
    )


@pytest.mark.asyncio
async def test_entities_list_forwards_ordering_skip_and_shaping_params():
    """Test generic list() forwards order_by/order_by_desc/skip and the shaping params."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    # scripted_list declares RequestHandler.list's own signature, so an
    # unsupported argument from the caller fails here rather than being
    # swallowed by a fake.
    mock_list, seen = scripted_list([{"ResourceType": "UserStory", "Id": 1, "Name": "Story 1"}])
    mock_request_handler.list = mock_list

    resource = EntitiesResource(mock_client, mock_request_handler)

    results = [
        item
        async for item in resource.list(
            "UserStory",
            exclude=["Description"],
            result_include=["Id"],
            append=["Tasks-Count"],
            innertake=4,
            order_by_desc="Name",
            skip=25,
        )
    ]

    assert len(results) == 1
    assert seen["entity_type"] == "UserStory"
    assert seen["exclude"] == ["Description"]
    assert seen["result_include"] == ["Id"]
    assert seen["append"] == ["Tasks-Count"]
    assert seen["innertake"] == 4
    assert seen["order_by"] is None
    assert seen["order_by_desc"] == "Name"
    assert seen["skip"] == 25
