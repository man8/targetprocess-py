"""Tests for UsersResource."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from targetprocess import TargetProcessClient
from targetprocess.exceptions import NotFoundError, ParseError
from targetprocess.models import User
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.users import UsersResource
from targetprocess.types import ClientMode

_LOGGED_USER_PATH = "/api/v1/Users/LoggedUser"

_USER_BODY: dict[str, Any] = {
    "ResourceType": "User",
    "Id": 342,
    "FirstName": "Alex",
    "LastName": "Example",
    "Login": "alex",
    "FullName": "Alex Example",
    "IsActive": True,
}


@pytest.mark.asyncio
async def test_users_resource_entity_type():
    """Test UsersResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = UsersResource(mock_client, mock_request_handler)

    assert resource.entity_type == "User"
    assert resource.model_class == User


@pytest.mark.asyncio
async def test_users_inherits_crud():
    """Test UsersResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = UsersResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")


def _resource(handler: Mock) -> UsersResource:
    """A UsersResource over a mocked handler, on a READONLY client."""
    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READONLY
    return UsersResource(client, handler)


def _handler(*results: Any) -> Mock:
    """A mocked handler whose logged_user() answers each result in turn (raising exceptions)."""
    handler = Mock(spec=RequestHandler)
    handler.logged_user = AsyncMock(side_effect=list(results))
    return handler


async def test_logged_user_parses_the_route_body_into_a_user() -> None:
    handler = _handler(_USER_BODY)
    resource = _resource(handler)

    user = await resource.logged_user()

    handler.logged_user.assert_awaited_once_with()
    assert isinstance(user, User)
    assert user.id == 342
    assert user.login == "alex"
    assert user.resource_type == "User"


async def test_logged_user_is_cached_on_the_resource() -> None:
    handler = _handler(_USER_BODY)
    resource = _resource(handler)

    first = await resource.logged_user()
    second = await resource.logged_user()

    assert second is first
    assert handler.logged_user.await_count == 1


async def test_logged_user_raises_the_parse_error_users_get_raises() -> None:
    body = {"ResourceType": "User", "Login": "alex"}  # no Id
    handler = _handler(body)
    handler.get = AsyncMock(return_value=body)
    resource = _resource(handler)

    with pytest.raises(ParseError) as from_get:
        await resource.get(342)
    with pytest.raises(ParseError) as from_logged_user:
        await resource.logged_user()

    assert str(from_logged_user.value) == str(from_get.value)
    assert str(from_logged_user.value).startswith("failed to parse User:")


async def test_logged_user_caches_nothing_on_a_parse_failure() -> None:
    handler = _handler({"ResourceType": "User"}, _USER_BODY)
    resource = _resource(handler)

    with pytest.raises(ParseError):
        await resource.logged_user()
    user = await resource.logged_user()

    assert user.id == 342
    assert handler.logged_user.await_count == 2


async def test_logged_user_propagates_a_failed_read_and_caches_nothing() -> None:
    handler = _handler(NotFoundError("Not found"), _USER_BODY)
    resource = _resource(handler)

    with pytest.raises(NotFoundError):
        await resource.logged_user()
    user = await resource.logged_user()

    assert user.id == 342
    assert handler.logged_user.await_count == 2


def _client(handle: Callable[[httpx.Request], httpx.Response]) -> TargetProcessClient:
    """A real READONLY client, its real handler and resources, over a mock transport."""
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="secret-token", mode=ClientMode.READONLY
    )
    client._transport._client._transport = httpx.MockTransport(handle)
    return client


async def test_logged_user_is_one_request_per_client_instance() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_USER_BODY)

    client = _client(handle)
    first = await client.users.logged_user()
    second = await client.users.logged_user()

    assert second is first
    assert [(r.method, r.url.path) for r in requests] == [("GET", _LOGGED_USER_PATH)]

    other = _client(handle)
    fresh = await other.users.logged_user()

    assert fresh is not first
    assert fresh.id == first.id
    assert len(requests) == 2
