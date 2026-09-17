"""Tests for RequestHandler.logged_user - the fixed-path GET /api/v1/Users/LoggedUser read."""

from typing import Any

import httpx
import pytest

from targetprocess.exceptions import AuthenticationError
from tests._support.request_handler import (
    handler_with_mock_transport as _handler_with_mock_transport,
)

_USER_BODY = {"ResourceType": "User", "Id": 342, "Login": "alex"}


async def test_logged_user_gets_the_fixed_path_with_format_json() -> None:
    """logged_user() sends one GET to /api/v1/Users/LoggedUser with format=json and the token."""
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_USER_BODY)

    handler = _handler_with_mock_transport(handle)

    data = await handler.logged_user()

    assert data == _USER_BODY
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "GET"
    assert request.url.path == "/api/v1/Users/LoggedUser"
    assert request.url.params["format"] == "json"
    # Merged in by the transport's auth at send time.
    assert "access_token" in request.url.params
    assert set(request.url.params.keys()) == {"format", "access_token"}


async def test_logged_user_maps_an_error_status() -> None:
    """A 401 surfaces through _request's status mapping, as on any read."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"Error": "Unauthorized"})

    handler = _handler_with_mock_transport(handle)

    with pytest.raises(AuthenticationError):
        await handler.logged_user()


async def test_logged_user_retries_a_retryable_status(handler_scripted: Any) -> None:
    """Being a GET, logged_user() is retried on a 5xx like any other read."""
    handler, request_count, sleep_calls = handler_scripted([503, 200])

    data = await handler.logged_user()

    assert data["Id"] == 1
    assert request_count() == 2
    assert len(sleep_calls) == 1
