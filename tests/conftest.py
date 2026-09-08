"""Shared fixtures: RequestHandler instances over scripted mock transports."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from targetprocess.request_handler import RequestHandler
from tests._support.request_handler import handler_with_mock_transport


@pytest.fixture
def handler_with_capture() -> tuple[RequestHandler, list[httpx.Request]]:
    """Handler that always returns a single-item page; captures every request."""
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"Items": [{"Id": 1}], "Next": None})

    return handler_with_mock_transport(handle), captured


@pytest.fixture
def handler_with_response() -> Any:
    """Factory: handler that always returns the given JSON body."""

    def _make(response_json: dict[str, Any]) -> RequestHandler:
        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=response_json)

        return handler_with_mock_transport(handle)

    return _make


@pytest.fixture
def handler_with_connect_error() -> RequestHandler:
    """Handler whose transport fails at the connection level (no response)."""

    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return handler_with_mock_transport(handle)


@pytest.fixture
def handler_returning_pages() -> Any:
    """Factory: handler serving `total` items in pages of `page`, via real Next URLs.

    The first request has no `skip` (server default 0); each response's
    `Next` is an absolute URL carrying the server's own `skip`/`take` -
    RequestHandler must follow it verbatim rather than recomputing skip
    locally. `capture_urls=True` also returns the list of every request URL
    seen (post-auth, so `access_token` is present).
    """

    def _make(
        total: int, page: int, capture_urls: bool = False
    ) -> RequestHandler | tuple[RequestHandler, list[httpx.URL]]:
        urls: list[httpx.URL] = []
        base = "https://example.tpondemand.com/api/v1/UserStories"

        def handle(request: httpx.Request) -> httpx.Response:
            urls.append(request.url)
            skip = int(request.url.params.get("skip", "0"))
            take = int(request.url.params.get("take", str(page)))
            end = min(skip + take, total)
            items = [{"Id": i} for i in range(skip + 1, end + 1)]
            next_url = f"{base}?format=json&take={take}&skip={end}" if end < total else None
            return httpx.Response(200, json={"Items": items, "Next": next_url})

        handler = handler_with_mock_transport(handle)
        if capture_urls:
            return handler, urls
        return handler

    return _make


@pytest.fixture
def handler_scripted() -> Any:
    """Factory: handler serving a scripted sequence of status codes, one per request.

    Returns ``(handler, request_count, sleep_calls)``:
    - ``request_count()`` reports how many requests have been sent so far.
    - ``sleep_calls`` is the list of delays passed to the injected fake sleep
      (which never actually sleeps), in call order.

    Requests past the end of the scripted sequence repeat the last status,
    so a test only needs to script as many statuses as it cares about.
    """

    def _make(
        statuses: list[int], retry_after: dict[int, str] | None = None
    ) -> tuple[RequestHandler, Callable[[], int], list[float]]:
        count = 0
        sleeps: list[float] = []

        def handle(request: httpx.Request) -> httpx.Response:
            nonlocal count
            status = statuses[min(count, len(statuses) - 1)]
            count += 1
            headers = (
                {"Retry-After": retry_after[status]}
                if retry_after and status in retry_after
                else {}
            )
            body = (
                {"Id": 1, "Name": "Story", "ResourceType": "UserStory"}
                if status < 400
                else {"Error": f"HTTP {status}"}
            )
            return httpx.Response(status, json=body, headers=headers)

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        handler = handler_with_mock_transport(handle, sleep=fake_sleep)
        return handler, (lambda: count), sleeps

    return _make
