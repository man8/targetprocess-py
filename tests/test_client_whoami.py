"""Tests for TargetProcessClient.whoami and its current_user alias."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from targetprocess import ClientMode, TargetProcessClient
from targetprocess.client import _logged_user
from targetprocess.exceptions import NotFoundError, ParseError
from targetprocess.models import User

_CONTEXT_PATH = "/api/v1/Context"
_USER_PATH = "/api/v1/User/342"

# Context carries the acting user's identity but no Login.
_CONTEXT_BODY: dict[str, Any] = {
    "ResourceType": "Context",
    "LoggedUser": {
        "ResourceType": "User",
        "Id": 342,
        "Email": "alex@example.com",
        "FirstName": "Alex",
        "LastName": "Example",
        "Kind": "User",
        "IsActive": True,
        "IsAdministrator": False,
    },
    "SelectedTeams": {"Items": []},
}

_USER_BODY: dict[str, Any] = {
    "ResourceType": "User",
    "Id": 342,
    "Email": "alex@example.com",
    "FirstName": "Alex",
    "LastName": "Example",
    "Login": "alex",
    "FullName": "Alex Example",
    "IsActive": True,
}


def _client(handle: Callable[[httpx.Request], httpx.Response]) -> TargetProcessClient:
    """A real READONLY client, its real handler and resources, over a mock transport."""
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="secret-token", mode=ClientMode.READONLY
    )
    client._transport._client._transport = httpx.MockTransport(handle)
    return client


def _routed(
    context: httpx.Response | None = None, user: httpx.Response | None = None
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    """A handler answering the Context and User paths, recording every request."""
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == _CONTEXT_PATH:
            return context or httpx.Response(200, json=_CONTEXT_BODY)
        if request.url.path == _USER_PATH:
            return user or httpx.Response(200, json=_USER_BODY)
        return httpx.Response(404, json={"Error": f"unexpected path {request.url.path}"})

    return handle, requests


async def test_whoami_reads_logged_user_then_hydrates_via_users_get() -> None:
    handle, requests = _routed()
    client = _client(handle)

    user = await client.whoami()

    assert [r.url.path for r in requests] == [_CONTEXT_PATH, _USER_PATH]
    assert all(r.method == "GET" for r in requests)
    assert isinstance(user, User)
    assert user.id == 342
    assert user.login == "alex"
    assert user.resource_type == "User"


async def test_whoami_is_cached_for_the_client_lifetime() -> None:
    handle, requests = _routed()
    client = _client(handle)

    first = await client.whoami()
    second = await client.whoami()

    assert len(requests) == 2
    assert second is first


async def test_current_user_is_an_alias_of_whoami() -> None:
    handle, requests = _routed()
    client = _client(handle)

    user = await client.whoami()
    alias = await client.current_user()

    assert alias is user
    assert len(requests) == 2

    fresh_handle, fresh_requests = _routed()
    fresh = _client(fresh_handle)

    resolved = await fresh.current_user()

    assert [r.url.path for r in fresh_requests] == [_CONTEXT_PATH, _USER_PATH]
    assert resolved.id == 342
    assert await fresh.whoami() is resolved
    assert len(fresh_requests) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"ResourceType": "Context"},
        {"ResourceType": "Context", "LoggedUser": None},
        {"ResourceType": "Context", "LoggedUser": {"ResourceType": "User"}},
    ],
    ids=["missing", "null", "no-id"],
)
async def test_whoami_raises_parse_error_without_a_usable_logged_user(
    body: dict[str, Any],
) -> None:
    handle, requests = _routed(context=httpx.Response(200, json=body))
    client = _client(handle)

    with pytest.raises(ParseError, match="LoggedUser.*Context"):
        await client.whoami()
    assert [r.url.path for r in requests] == [_CONTEXT_PATH]

    # Nothing was cached, so the next call asks Context again.
    with pytest.raises(ParseError):
        await client.whoami()
    assert [r.url.path for r in requests] == [_CONTEXT_PATH, _CONTEXT_PATH]


async def test_whoami_propagates_a_failed_hydration_and_caches_nothing() -> None:
    handle, requests = _routed(user=httpx.Response(404, json={"Error": "Not found"}))
    client = _client(handle)

    with pytest.raises(NotFoundError):
        await client.whoami()
    assert [r.url.path for r in requests] == [_CONTEXT_PATH, _USER_PATH]

    with pytest.raises(NotFoundError):
        await client.whoami()
    assert [r.url.path for r in requests] == [_CONTEXT_PATH, _USER_PATH] * 2


async def test_whoami_sends_no_projection() -> None:
    handle, requests = _routed()
    client = _client(handle)

    await client.whoami()

    context_request = requests[0]
    assert context_request.url.path == _CONTEXT_PATH
    assert set(context_request.url.params.keys()) == {"format", "access_token"}
    assert context_request.url.params["format"] == "json"


@pytest.mark.parametrize(
    "data",
    [{"ResourceType": "Context", "LoggedUser": "alex"}, ["LoggedUser"]],
    ids=["string-logged-user", "non-object-body"],
)
def test_logged_user_helper_rejects_a_non_object(data: Any) -> None:
    with pytest.raises(ParseError, match="LoggedUser"):
        _logged_user(data)


def test_logged_user_helper_ignores_undeclared_fields() -> None:
    ref = _logged_user(_CONTEXT_BODY)

    assert ref.id == 342
    assert ref.first_name == "Alex"
    assert ref.login is None
