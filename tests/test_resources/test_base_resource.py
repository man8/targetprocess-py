"""Tests for BaseResource base class."""

from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from targetprocess.client import TargetProcessClient
from targetprocess.exceptions import AmbiguousMatchError, NotFoundError, ReadOnlyViolation
from targetprocess.models import NamedEntity, UserStory
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.base import BaseResource, _resolve_by_name
from targetprocess.types import ClientMode


class TestResource(BaseResource[UserStory]):
    """Test resource for BaseResource tests."""

    entity_type = "UserStory"
    model_class = UserStory


@pytest.mark.asyncio
async def test_get_delegates_to_request_handler():
    """Test that get() delegates to RequestHandler."""
    # Arrange
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()
    expected_story = UserStory(id=123, name="Test Story", resource_type="UserStory")
    mock_request_handler.get.return_value = expected_story

    resource = TestResource(mock_client, mock_request_handler)

    # Act
    result = await resource.get(123)

    # Assert
    assert result == expected_story
    mock_request_handler.get.assert_called_once_with(
        "UserStory",
        123,
        include=None,
        exclude=None,
        result_include=None,
        append=None,
        innertake=None,
    )


@pytest.mark.asyncio
async def test_list_delegates_to_request_handler():
    """Test that list() delegates to RequestHandler, forwarding where/limit/page_size."""
    # Arrange
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()
    captured_calls: list[tuple[tuple, dict]] = []

    async def mock_list(*args, **kwargs):
        captured_calls.append((args, kwargs))
        yield UserStory(id=1, name="Story 1", resource_type="UserStory")
        yield UserStory(id=2, name="Story 2", resource_type="UserStory")

    mock_request_handler.list = mock_list

    resource = TestResource(mock_client, mock_request_handler)

    # Act
    results = [
        item
        async for item in resource.list(
            where="(EntityState.IsFinal eq 'false')", limit=10, page_size=5
        )
    ]

    # Assert
    assert len(results) == 2
    assert results[0].id == 1
    assert results[1].id == 2
    assert len(captured_calls) == 1
    args, kwargs = captured_calls[0]
    assert args == ("UserStory",)
    assert kwargs["where"] == "(EntityState.IsFinal eq 'false')"
    assert kwargs["limit"] == 10
    assert kwargs["page_size"] == 5


@pytest.mark.asyncio
async def test_create_checks_write_permission():
    """Test that create() checks write permission."""
    # Arrange
    mock_client = Mock()
    mock_client._check_write_permission = Mock()
    mock_request_handler = AsyncMock()
    expected_story = UserStory(id=123, name="New Story", resource_type="UserStory")
    mock_request_handler.create.return_value = expected_story

    resource = TestResource(mock_client, mock_request_handler)

    # Act
    result = await resource.create(name="New Story")

    # Assert
    assert result == expected_story
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.create.assert_called_once_with("UserStory", {"name": "New Story"})


@pytest.mark.asyncio
async def test_update_checks_write_permission():
    """Test that update() checks write permission."""
    # Arrange
    mock_client = Mock()
    mock_client._check_write_permission = Mock()
    mock_request_handler = AsyncMock()
    expected_story = UserStory(id=123, name="Updated Story", resource_type="UserStory")
    mock_request_handler.update.return_value = expected_story

    resource = TestResource(mock_client, mock_request_handler)

    # Act
    result = await resource.update(123, name="Updated Story")

    # Assert
    assert result == expected_story
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.update.assert_called_once_with("UserStory", 123, {"name": "Updated Story"})


@pytest.mark.asyncio
async def test_delete_checks_write_permission():
    """Test that delete() checks write permission."""
    # Arrange
    mock_client = Mock()
    mock_client._check_write_permission = Mock()
    mock_request_handler = AsyncMock()
    mock_request_handler.delete.return_value = None

    resource = TestResource(mock_client, mock_request_handler)

    # Act
    await resource.delete(123)

    # Assert
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.delete.assert_called_once_with("UserStory", 123)


@pytest.mark.asyncio
async def test_create_many_delegates_to_bulk_and_parses():
    """create_many() checks write permission, delegates to bulk, and parses each item."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.bulk.return_value = [
        {"Id": 1, "Name": "First", "ResourceType": "UserStory"},
        {"Id": 2, "Name": "Second", "ResourceType": "UserStory"},
    ]

    resource = TestResource(mock_client, mock_request_handler)

    items = [{"Name": "First"}, {"Name": "Second"}]
    result = await resource.create_many(items)

    assert [story.id for story in result] == [1, 2]
    assert all(isinstance(story, UserStory) for story in result)
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.bulk.assert_called_once_with("UserStory", items)


@pytest.mark.asyncio
async def test_create_many_rejects_item_with_id():
    """create_many() refuses an Id-bearing item before any request is sent."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = TestResource(mock_client, mock_request_handler)

    with pytest.raises(ValueError, match="update_many"):
        await resource.create_many([{"Name": "ok"}, {"Id": 5, "Name": "bad"}])
    # The wire field is ``Id``; a lowercase spelling is the same mistake.
    with pytest.raises(ValueError, match="'id'"):
        await resource.create_many([{"id": 5, "Name": "bad"}])

    mock_request_handler.bulk.assert_not_called()


@pytest.mark.asyncio
async def test_update_many_delegates_to_bulk_and_parses():
    """update_many() checks write permission, delegates to bulk, and parses each item."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.bulk.return_value = [
        {"Id": 1, "Name": "Renamed", "ResourceType": "UserStory"},
    ]

    resource = TestResource(mock_client, mock_request_handler)

    items = [{"Id": 1, "Name": "Renamed"}]
    result = await resource.update_many(items)

    assert [story.id for story in result] == [1]
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.bulk.assert_called_once_with("UserStory", items)


@pytest.mark.asyncio
async def test_update_many_rejects_item_without_id():
    """update_many() refuses an Id-less item before any request is sent."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = TestResource(mock_client, mock_request_handler)

    with pytest.raises(ValueError, match="create_many"):
        await resource.update_many([{"Id": 1}, {"Name": "no id"}])

    mock_request_handler.bulk.assert_not_called()


@pytest.mark.asyncio
async def test_update_many_rejects_duplicate_id_keys():
    """An item spelling the identifier twice (``Id`` and ``id``) is ambiguous and refused."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = TestResource(mock_client, mock_request_handler)

    with pytest.raises(ValueError, match="more than one Id key"):
        await resource.update_many([{"Id": 1, "id": 2, "Name": "which?"}])

    mock_request_handler.bulk.assert_not_called()


@pytest.mark.asyncio
async def test_update_many_accepts_lowercase_id_key():
    """A lowercase ``id`` passes update_many's shape check and is sent to the wire as ``Id``."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.bulk.return_value = [{"Id": 1, "ResourceType": "UserStory"}]

    resource = TestResource(mock_client, mock_request_handler)

    result = await resource.update_many([{"id": 1, "Name": "Renamed"}])

    assert [story.id for story in result] == [1]
    mock_request_handler.bulk.assert_called_once_with("UserStory", [{"Id": 1, "Name": "Renamed"}])


@pytest.mark.asyncio
async def test_bulk_methods_refused_on_server_read_only_collection():
    """create_many/update_many raise on a server-read-only collection in any mode."""

    class _ServerReadOnlyResource(BaseResource[UserStory]):
        entity_type = "UserStory"
        model_class = UserStory
        server_read_only = True

    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = _ServerReadOnlyResource(mock_client, mock_request_handler)

    with pytest.raises(ReadOnlyViolation):
        await resource.create_many([{"Name": "x"}])
    with pytest.raises(ReadOnlyViolation):
        await resource.update_many([{"Id": 1}])

    mock_client._check_write_permission.assert_not_called()
    mock_request_handler.bulk.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_methods_blocked_in_readonly_mode():
    """The full path raises ReadOnlyViolation on a READONLY client, before the wire."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("readonly guard did not fire")

    client._transport._client._transport = httpx.MockTransport(handle)

    with pytest.raises(ReadOnlyViolation):
        await client.user_stories.create_many([{"Name": "x"}])
    with pytest.raises(ReadOnlyViolation):
        await client.user_stories.update_many([{"Id": 1}])


@pytest.mark.asyncio
async def test_bulk_methods_empty_items_make_no_request():
    """The full READWRITE path short-circuits an empty batch without a request."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READWRITE,
    )

    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be sent for an empty batch")

    client._transport._client._transport = httpx.MockTransport(handle)

    assert await client.user_stories.create_many([]) == []
    assert await client.user_stories.update_many([]) == []


async def test_get_forwards_shaping_params():
    """Test that get() forwards the shaping params to RequestHandler."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.get.return_value = {
        "Id": 123,
        "ResourceType": "UserStory",
        "Name": "Test Story",
    }

    resource = TestResource(mock_client, mock_request_handler)

    result = await resource.get(
        123,
        include=["Name"],
        exclude=["Description"],
        result_include=["Id"],
        append=["Tasks-Count"],
        innertake=5,
    )

    assert result.id == 123
    mock_request_handler.get.assert_called_once_with(
        "UserStory",
        123,
        include=["Name"],
        exclude=["Description"],
        result_include=["Id"],
        append=["Tasks-Count"],
        innertake=5,
    )


@pytest.mark.asyncio
async def test_list_forwards_ordering_skip_and_shaping_params():
    """Test that list() forwards order_by/order_by_desc/skip and the shaping params."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    captured_calls: list[tuple[tuple, dict]] = []

    async def mock_list(
        entity_type: str,
        *,
        where: str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        result_include: list[str] | None = None,
        append: list[str] | None = None,
        innertake: int | None = None,
        order_by: str | None = None,
        order_by_desc: str | None = None,
        skip: int | None = None,
        limit: int | None = None,
        page_size: int = 25,
    ):
        # Same interface as RequestHandler.list, so an unsupported argument
        # from the caller fails here rather than being swallowed by a fake.
        captured_calls.append(
            (
                (entity_type,),
                {
                    "where": where,
                    "include": include,
                    "exclude": exclude,
                    "result_include": result_include,
                    "append": append,
                    "innertake": innertake,
                    "order_by": order_by,
                    "order_by_desc": order_by_desc,
                    "skip": skip,
                    "limit": limit,
                    "page_size": page_size,
                },
            )
        )
        yield {"Id": 1, "ResourceType": "UserStory", "Name": "Story 1"}

    mock_request_handler.list = mock_list

    resource = TestResource(mock_client, mock_request_handler)

    results = [
        item
        async for item in resource.list(
            exclude=["Description"],
            result_include=["Id"],
            append=["Tasks-Count"],
            innertake=3,
            order_by="Name",
            skip=10,
        )
    ]

    assert len(results) == 1
    args, kwargs = captured_calls[0]
    assert args == ("UserStory",)
    assert kwargs["exclude"] == ["Description"]
    assert kwargs["result_include"] == ["Id"]
    assert kwargs["append"] == ["Tasks-Count"]
    assert kwargs["innertake"] == 3
    assert kwargs["order_by"] == "Name"
    assert kwargs["order_by_desc"] is None
    assert kwargs["skip"] == 10


def test_server_permits_every_operation_by_default():
    """A plain subclass declares nothing, so the server is taken to accept every write."""
    assert all(TestResource.server_permits(op) for op in ("create", "update", "delete"))


@pytest.mark.asyncio
async def test_partial_server_capability_refuses_only_the_missing_operations():
    """A per-operation flag refuses exactly its operation, pre-request, and no other."""

    class _UpdateOnlyResource(BaseResource[UserStory]):
        entity_type = "UserStory"
        model_class = UserStory
        server_can_create = False
        server_can_delete = False

    assert not _UpdateOnlyResource.server_permits("create")
    assert _UpdateOnlyResource.server_permits("update")
    assert not _UpdateOnlyResource.server_permits("delete")

    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.update.return_value = {"Id": 1, "Name": "Renamed"}
    resource = _UpdateOnlyResource(mock_client, mock_request_handler)

    with pytest.raises(ReadOnlyViolation, match="does not accept create on the server"):
        await resource.create(Name="x")
    with pytest.raises(ReadOnlyViolation, match="does not accept create on the server"):
        await resource.create_many([{"Name": "x"}])
    with pytest.raises(ReadOnlyViolation, match="does not accept delete on the server"):
        await resource.delete(1)
    # The refusal precedes the mode gate - mode never came into it.
    mock_client._check_write_permission.assert_not_called()
    mock_request_handler.create.assert_not_called()
    mock_request_handler.bulk.assert_not_called()
    mock_request_handler.delete.assert_not_called()

    updated = await resource.update(1, Name="Renamed")
    assert updated.name == "Renamed"
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.update.assert_called_once_with("UserStory", 1, {"Name": "Renamed"})


def test_server_read_only_overrides_the_per_operation_flags():
    """The blanket flag wins even where a per-operation flag says True."""

    class _ContradictoryResource(BaseResource[UserStory]):
        entity_type = "UserStory"
        model_class = UserStory
        server_read_only = True
        server_can_update = True

    assert not _ContradictoryResource.server_permits("update")
    refusal = _ContradictoryResource._server_refusal("update", "UserStory")
    assert "read-only on the server" in str(refusal)
    assert refusal.operation == "update"
    assert refusal.resource == "UserStory"


def _named(*pairs: tuple[int, str | None]) -> list[NamedEntity]:
    return [NamedEntity.model_validate({"Id": id, "Name": name}) for id, name in pairs]


def test_resolve_by_name_matches_case_insensitively():
    match = _resolve_by_name(_named((1, "Developer"), (2, "QA Engineer")), "developer", what="role")
    assert match.id == 1


def test_resolve_by_name_lists_the_available_names_when_absent():
    with pytest.raises(NotFoundError) as excinfo:
        _resolve_by_name(_named((1, "Developer"), (2, None), (3, "Tester")), "Ops", what="role")
    # Sorted, the None-named record skipped, the noun from the caller.
    assert str(excinfo.value) == "no role named 'Ops'; available: Developer, Tester"


def test_resolve_by_name_reports_none_available_on_an_empty_set():
    with pytest.raises(NotFoundError, match="available: none"):
        _resolve_by_name(_named(), "Ops", what="role")


def test_resolve_by_name_refuses_to_guess_between_duplicates():
    with pytest.raises(AmbiguousMatchError) as excinfo:
        _resolve_by_name(_named((1, "Developer"), (9, "developer")), "Developer", what="role")
    assert str(excinfo.value) == "role 'Developer' matched 2 records (Ids: 1, 9)"


def test_check_include_accepts_everything_by_default():
    """A resource declaring no unhydratable includes refuses nothing - the common case."""
    assert TestResource.unhydratable_includes == {}
    TestResource.check_include(None)
    TestResource.check_include(["Name", "CustomFields", "Comments[Id]"])


@pytest.mark.asyncio
async def test_unhydratable_include_is_refused_before_any_request():
    """A declared collision is refused by leading identifier, in any casing, pre-request."""

    class _CollidingResource(BaseResource[UserStory]):
        entity_type = "UserStory"
        model_class = UserStory
        unhydratable_includes = {"Comments": "use client.comments instead"}

    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    resource = _CollidingResource(mock_client, mock_request_handler)

    for field in ("Comments", "COMMENTS", " comments[Id] "):
        with pytest.raises(ValueError, match="use client.comments instead"):
            await resource.get(1, include=[field])
        with pytest.raises(ValueError, match="use client.comments instead"):
            async for _ in resource.list(include=[field]):
                pass
    mock_request_handler.get.assert_not_called()
    mock_request_handler.list.assert_not_called()

    # A different field, and a field merely containing the name, both pass.
    mock_request_handler.get.return_value = {"Id": 1, "Name": "ok"}
    await resource.get(1, include=["Name", "CommentsCount"])
    mock_request_handler.get.assert_awaited_once()
