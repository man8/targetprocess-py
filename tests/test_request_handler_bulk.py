"""Tests for RequestHandler.bulk - the POST /{collection}/bulk path."""

import json
from typing import Any

import httpx
import pytest

from targetprocess.exceptions import APIError, ParseError, RateLimitError, ReadOnlyViolation
from targetprocess.request_handler import RequestHandler
from targetprocess.transport import HTTPTransport
from tests._support.request_handler import (
    handler_with_mock_transport as _handler_with_mock_transport,
)


async def test_bulk_posts_array_to_bulk_endpoint() -> None:
    """bulk() POSTs the items array to /{collection}/bulk and returns the response list."""
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json=[
                {"Id": 999, "Name": "First", "ResourceType": "UserStory"},
                {"Id": 1000, "Name": "Second", "ResourceType": "UserStory"},
            ],
        )

    handler = _handler_with_mock_transport(handle)

    items = [
        {"Name": "First", "Project": {"Id": 2}},
        {"Name": "Second", "Project": {"Id": 2}},
    ]
    data = await handler.bulk("UserStories", items)

    assert [entry["Id"] for entry in data] == [999, 1000]
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/UserStories/bulk"
    assert json.loads(request.content) == items


async def test_bulk_unwraps_items_envelope(handler_with_response: Any) -> None:
    """bulk() also accepts an Items-wrapped response body.

    TargetProcess does not document the bulk response's shape, so both a
    bare array and the collection-style Items envelope are accepted.
    """
    handler = handler_with_response({"Items": [{"Id": 7, "ResourceType": "Bug"}]})

    data = await handler.bulk("Bugs", [{"Name": "crash"}])

    assert data == [{"Id": 7, "ResourceType": "Bug"}]


async def test_bulk_unrecognised_response_shape_raises_parse_error(
    handler_with_response: Any,
) -> None:
    """A bulk response that is neither an array nor Items-wrapped raises ParseError."""
    handler = handler_with_response({"Message": "ok"})

    with pytest.raises(ParseError, match="bulk response"):
        await handler.bulk("Bugs", [{"Name": "crash"}])


async def test_bulk_rejects_non_object_items_in_bare_array(
    handler_with_response: Any,
) -> None:
    """A bare-array bulk response containing a non-object raises ParseError."""
    handler = handler_with_response([{"Id": 7, "ResourceType": "Bug"}, None])

    with pytest.raises(ParseError, match="bulk response"):
        await handler.bulk("Bugs", [{"Name": "crash"}])


async def test_bulk_rejects_non_object_items_in_items_envelope(
    handler_with_response: Any,
) -> None:
    """An Items-wrapped bulk response containing a non-object raises ParseError."""
    handler = handler_with_response({"Items": [None]})

    with pytest.raises(ParseError, match="bulk response"):
        await handler.bulk("Bugs", [{"Name": "crash"}])


async def test_bulk_empty_items_makes_no_request() -> None:
    """An empty items list returns [] without any network request."""
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=[])

    handler = _handler_with_mock_transport(handle)

    assert await handler.bulk("UserStories", []) == []
    assert captured == []


async def test_bulk_write_gated() -> None:
    """bulk() consults check_write before sending anything - empty batch included."""
    requests_sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests_sent.append(request)
        return httpx.Response(200, json=[])

    def refuse() -> None:
        raise ReadOnlyViolation()

    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    transport._client._transport = httpx.MockTransport(handle)
    handler = RequestHandler(transport, check_write=refuse)

    with pytest.raises(ReadOnlyViolation):
        await handler.bulk("UserStories", [{"Name": "New Story"}])
    with pytest.raises(ReadOnlyViolation):
        await handler.bulk("UserStories", [])

    assert requests_sent == []


async def test_bulk_429_never_retried(handler_scripted: Any) -> None:
    """A 429 on a bulk POST raises immediately - bulk inherits the mutation retry policy."""
    handler, request_count, sleeps = handler_scripted([429], retry_after={429: "0"})

    with pytest.raises(RateLimitError):
        await handler.bulk("UserStories", [{"Name": "New Story"}])

    assert request_count() == 1
    assert sleeps == []


async def test_bulk_5xx_never_retried(handler_scripted: Any) -> None:
    """A 5xx on a bulk POST raises immediately - part of the array may be committed."""
    handler, request_count, sleeps = handler_scripted([500])

    with pytest.raises(APIError):
        await handler.bulk("UserStories", [{"Name": "New Story"}])

    assert request_count() == 1
    assert sleeps == []
