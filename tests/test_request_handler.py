"""Tests for RequestHandler."""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from targetprocess.exceptions import (
    APIError,
    NetworkError,
    NotFoundError,
    ParseError,
    RateLimitError,
    ReadOnlyViolation,
    TargetProcessError,
)
from targetprocess.models import UserStory
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.base import BaseResource
from targetprocess.transport import HTTPTransport
from tests._support.request_handler import (
    handler_with_mock_transport as _handler_with_mock_transport,
)


@pytest.mark.asyncio
async def test_request_handler_initialization() -> None:
    """Test RequestHandler initializes with HTTPTransport."""
    transport = HTTPTransport(
        domain="example.tpondemand.com",
        token="test-token",
    )

    handler = RequestHandler(transport)

    assert handler._transport is transport
    assert handler._rate_limiter is not None


@pytest.mark.asyncio
async def test_request_with_rate_limiting() -> None:
    """Test _request method applies rate limiting."""
    transport = Mock(HTTPTransport)
    transport._client = Mock()
    transport._client.request = AsyncMock(return_value=httpx.Response(200, json={"Id": 123}))

    handler = RequestHandler(transport)

    response = await handler._request("GET", "https://example.com/api/v1/UserStories/123")

    assert response.status_code == 200
    transport._client.request.assert_called_once_with(
        "GET",
        "https://example.com/api/v1/UserStories/123",
    )


@pytest.mark.asyncio
async def test_request_raises_on_error_status() -> None:
    """Test _request raises exception on error status."""
    from targetprocess.exceptions import NotFoundError

    transport = Mock(HTTPTransport)
    transport._client = Mock()
    transport._client.request = AsyncMock(
        return_value=httpx.Response(404, json={"Error": "Not found"})
    )

    handler = RequestHandler(transport)

    with pytest.raises(NotFoundError):
        await handler._request("GET", "https://example.com/api/v1/UserStories/99999")


@pytest.mark.asyncio
async def test_get_single_entity() -> None:
    """Test getting single entity by ID."""
    transport = Mock(HTTPTransport)
    transport.base_url = "https://example.tpondemand.com/api/v1"
    transport._client = Mock()
    transport._client.request = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"Id": 123, "Name": "Test Story", "ResourceType": "UserStory"},
        )
    )

    handler = RequestHandler(transport)

    data = await handler.get("UserStories", 123)

    assert data["Id"] == 123
    assert data["Name"] == "Test Story"
    # Verify URL construction
    call_args = transport._client.request.call_args
    assert call_args[0][0] == "GET"
    assert "UserStories/123" in call_args[0][1]
    assert "format=json" in call_args[0][1]


@pytest.mark.asyncio
async def test_get_with_include() -> None:
    """Test get with field inclusion."""
    transport = Mock(HTTPTransport)
    transport.base_url = "https://example.tpondemand.com/api/v1"
    transport._client = Mock()
    transport._client.request = AsyncMock(return_value=httpx.Response(200, json={"Id": 123}))

    handler = RequestHandler(transport)

    await handler.get("UserStories", 123, include=["Name", "EntityState"])

    # Verify include parameter in URL (URL-encoded: [ becomes %5B, ] becomes %5D, , becomes %2C)
    call_args = transport._client.request.call_args
    url = call_args[0][1]
    assert "include=%5BName%2CEntityState%5D" in url or "include=[Name,EntityState]" in url


@pytest.mark.asyncio
async def test_list_single_page(handler_with_response: Any) -> None:
    """Test list with single page of results (no Next)."""
    handler = handler_with_response(
        {
            "Items": [
                {"Id": 1, "Name": "First"},
                {"Id": 2, "Name": "Second"},
            ],
            "Next": None,
        }
    )

    items = [item async for item in handler.list("UserStories")]

    assert len(items) == 2
    assert items[0]["Id"] == 1
    assert items[1]["Id"] == 2


async def test_list_where_param_passed_through(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    handler, captured = handler_with_capture
    async for _ in handler.list("UserStories", where="(EntityState.IsFinal eq 'false')"):
        break
    assert captured[0].url.params["where"] == "(EntityState.IsFinal eq 'false')"


async def test_list_limit_caps_total_items(handler_returning_pages: Any) -> None:
    # server has 60 items in pages of 25; limit=30 must yield exactly 30
    handler = handler_returning_pages(total=60, page=25)
    items = [i async for i in handler.list("UserStories", limit=30)]
    assert len(items) == 30
    assert [item["Id"] for item in items] == list(range(1, 31))


async def test_list_follows_next_url(handler_returning_pages: Any) -> None:
    handler, urls = handler_returning_pages(total=60, page=25, capture_urls=True)
    items = [i async for i in handler.list("UserStories")]
    assert len(items) == 60
    assert [item["Id"] for item in items] == list(range(1, 61))
    # three requests: 25 + 25 + 10
    assert len(urls) == 3
    # second and third requests hit the server-provided Next URLs verbatim
    assert "skip" in str(urls[1])
    assert "skip" in str(urls[2])


async def test_list_next_url_keeps_inline_query_and_gains_access_token(
    handler_returning_pages: Any,
) -> None:
    """A Next request must retain its own inline query AND gain access_token.

    transport tests already prove the access_token half in isolation; this
    proves both hold simultaneously on the actual RequestHandler.list path.
    """
    handler, urls = handler_returning_pages(total=60, page=25, capture_urls=True)
    async for _ in handler.list("UserStories"):
        pass
    next_request_url = urls[1]
    assert next_request_url.params["access_token"] == "secret-token"
    assert next_request_url.params["skip"] == "25"
    assert next_request_url.params["take"] == "25"


async def test_list_null_items_ends_iteration(handler_with_response: Any) -> None:
    handler = handler_with_response({"Items": None})
    items = [i async for i in handler.list("UserStories")]
    assert items == []


async def test_list_rejects_next_url_on_different_host() -> None:
    """A fabricated Next pointing at a different host is rejected, not followed.

    The transport's auth merges the access_token into every request it
    sends, regardless of destination host - so blindly following an
    off-host Next would leak the token there (SSRF). The guard must raise
    before a second request is ever made.
    """
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "Items": [{"Id": 1}],
                "Next": "https://evil.example.com/api/v1/UserStories?skip=25",
            },
        )

    handler = _handler_with_mock_transport(handle)

    with pytest.raises(NetworkError):
        async for _ in handler.list("UserStories"):
            pass

    assert len(requests) == 1


async def test_list_limit_zero_yields_nothing_and_makes_no_requests(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    """limit=0 must yield zero items and never touch the network."""
    handler, captured = handler_with_capture
    items = [i async for i in handler.list("UserStories", limit=0)]
    assert items == []
    assert captured == []


async def test_get_shaping_params_passed_through(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    """get() renders exclude/resultInclude/append in TP's bracketed form, innertake plain."""
    handler, captured = handler_with_capture
    await handler.get(
        "UserStories",
        123,
        include=["Name"],
        exclude=["Description"],
        result_include=["Id"],
        append=["Tasks-Count"],
        innertake=5,
    )
    assert "UserStories/123" in str(captured[0].url)
    params = captured[0].url.params
    assert params["include"] == "[Name]"
    assert params["exclude"] == "[Description]"
    assert params["resultInclude"] == "[Id]"
    assert params["append"] == "[Tasks-Count]"
    assert params["innertake"] == "5"


async def test_get_omits_shaping_params_by_default(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    """A bare get() sends only format=json - no shaping param leaks in by default."""
    handler, captured = handler_with_capture
    await handler.get("UserStories", 123)
    params = captured[0].url.params
    for name in ("include", "exclude", "resultInclude", "append", "innertake"):
        assert name not in params


async def test_get_negative_innertake_raises(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    """A negative innertake raises before any request is sent."""
    handler, captured = handler_with_capture
    with pytest.raises(ValueError, match="innertake"):
        await handler.get("UserStories", 123, innertake=-1)
    assert captured == []


async def test_list_order_by_param_passed_through(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    handler, captured = handler_with_capture
    async for _ in handler.list("UserStories", order_by="Name"):
        break
    assert captured[0].url.params["orderBy"] == "Name"
    assert "orderByDesc" not in captured[0].url.params


async def test_list_order_by_desc_param_passed_through(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    handler, captured = handler_with_capture
    async for _ in handler.list("UserStories", order_by_desc="Name"):
        break
    assert captured[0].url.params["orderByDesc"] == "Name"
    assert "orderBy" not in captured[0].url.params


async def test_list_order_by_both_directions_raises(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    """order_by and order_by_desc together are refused before any request."""
    handler, captured = handler_with_capture
    with pytest.raises(ValueError, match="order_by"):
        async for _ in handler.list("UserStories", order_by="Name", order_by_desc="Id"):
            pass
    assert captured == []


async def test_list_shaping_params_passed_through(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    """list() renders the same shaping params as get()."""
    handler, captured = handler_with_capture
    async for _ in handler.list(
        "UserStories",
        exclude=["Description"],
        result_include=["Id"],
        append=["Tasks-Count"],
        innertake=3,
    ):
        break
    params = captured[0].url.params
    assert params["exclude"] == "[Description]"
    assert params["resultInclude"] == "[Id]"
    assert params["append"] == "[Tasks-Count]"
    assert params["innertake"] == "3"


async def test_list_omits_new_params_by_default(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    """A bare list() sends none of the new params - the Next-walk default is unchanged."""
    handler, captured = handler_with_capture
    async for _ in handler.list("UserStories"):
        break
    params = captured[0].url.params
    for name in (
        "orderBy",
        "orderByDesc",
        "skip",
        "exclude",
        "resultInclude",
        "append",
        "innertake",
    ):
        assert name not in params


async def test_list_skip_offsets_first_request_then_follows_next_verbatim(
    handler_returning_pages: Any,
) -> None:
    """skip= is sent on the first request only; continuation still follows Next.

    The forward-only safety property holds: the client never recomputes an
    offset - the caller's skip positions the start, and every later offset
    comes from the server's own Next URL.
    """
    handler, urls = handler_returning_pages(total=60, page=25, capture_urls=True)
    items = [i async for i in handler.list("UserStories", skip=10)]
    assert [item["Id"] for item in items] == list(range(11, 61))
    assert len(urls) == 2
    assert urls[0].params["skip"] == "10"
    # The continuation request carries the offset the server's Next URL named.
    # (The fixture's arithmetic Next makes 35 what a local recompute would also
    # produce; the verbatim-Next property itself is pinned by
    # test_list_next_url_keeps_inline_query_and_gains_access_token.)
    assert urls[1].params["skip"] == "35"


async def test_list_negative_skip_raises(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    handler, captured = handler_with_capture
    with pytest.raises(ValueError, match="skip"):
        async for _ in handler.list("UserStories", skip=-1):
            pass
    assert captured == []


async def test_list_negative_innertake_raises(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    """list() promises the same negative-innertake ValueError get() does."""
    handler, captured = handler_with_capture
    with pytest.raises(ValueError, match="innertake"):
        async for _ in handler.list("UserStories", innertake=-1):
            pass
    assert captured == []


async def test_list_validation_fires_even_with_limit_zero(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    """Invalid arguments raise even when limit=0 would short-circuit iteration."""
    handler, captured = handler_with_capture
    with pytest.raises(ValueError, match="skip"):
        async for _ in handler.list("UserStories", skip=-1, limit=0):
            pass
    assert captured == []


@pytest.mark.asyncio
async def test_create_entity() -> None:
    """Test creating new entity."""
    transport = Mock(HTTPTransport)
    transport.base_url = "https://example.tpondemand.com/api/v1"
    transport._client = Mock()
    transport._client.request = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"Id": 999, "Name": "New Story", "ResourceType": "UserStory"},
        )
    )

    handler = RequestHandler(transport)

    data = await handler.create("UserStories", {"Name": "New Story", "Project": {"Id": 42}})

    assert data["Id"] == 999
    # Verify POST request with JSON body
    call_args = transport._client.request.call_args
    assert call_args[0][0] == "POST"
    assert "UserStories" in call_args[0][1]


@pytest.mark.asyncio
async def test_update_entity() -> None:
    """Test updating existing entity."""
    transport = Mock(HTTPTransport)
    transport.base_url = "https://example.tpondemand.com/api/v1"
    transport._client = Mock()
    transport._client.request = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"Id": 123, "Name": "Updated Story"},
        )
    )

    handler = RequestHandler(transport)

    data = await handler.update("UserStories", 123, {"Name": "Updated Story"})

    assert data["Id"] == 123
    # Verify POST request (TargetProcess v1 uses POST for updates, not PUT)
    call_args = transport._client.request.call_args
    assert call_args[0][0] == "POST"
    assert "UserStories/123" in call_args[0][1]


@pytest.mark.asyncio
async def test_delete_entity() -> None:
    """Test deleting entity."""
    transport = Mock(HTTPTransport)
    transport.base_url = "https://example.tpondemand.com/api/v1"
    transport._client = Mock()
    transport._client.request = AsyncMock(
        return_value=httpx.Response(204)  # No content
    )

    handler = RequestHandler(transport)

    await handler.delete("UserStories", 123)

    # Verify DELETE request
    call_args = transport._client.request.call_args
    assert call_args[0][0] == "DELETE"
    assert "UserStories/123" in call_args[0][1]


async def test_network_error_wrapped(handler_with_connect_error: RequestHandler) -> None:
    """A transport-level failure (no response received) surfaces as NetworkError."""
    with pytest.raises(NetworkError):
        async for _ in handler_with_connect_error.list("UserStories"):
            pass


async def test_parse_error_wrapped(handler_with_response: Any) -> None:
    """resource layer: model_validate failure surfaces as ParseError, not raw pydantic."""

    class _UserStoriesResource(BaseResource[UserStory]):
        entity_type = "UserStory"
        model_class = UserStory

    handler = handler_with_response(
        {"Id": "not-an-int", "Name": "Bad", "ResourceType": "UserStory"}
    )
    resource = _UserStoriesResource(client=Mock(), request_handler=handler)

    with pytest.raises(ParseError) as exc_info:
        await resource.get(123)

    assert isinstance(exc_info.value, TargetProcessError)


async def test_retry_on_429_honours_retry_after(handler_scripted: Any) -> None:
    """A 429 with a numeric Retry-After retries once, honouring the header verbatim."""
    handler, request_count, sleeps = handler_scripted([429, 200], retry_after={429: "0"})

    data = await handler.get("UserStories", 1)

    assert data["Id"] == 1
    assert request_count() == 2
    assert sleeps == [0.0]


async def test_retry_gives_up_after_three(handler_scripted: Any) -> None:
    """Persistent 500s exhaust all retries (initial + 3) then map to APIError."""
    handler, request_count, sleeps = handler_scripted([500, 500, 500, 500])

    with pytest.raises(APIError):
        await handler.get("UserStories", 1)

    assert request_count() == 4
    assert sleeps == [0.5, 1.0, 2.0]


async def test_retry_exhaustion_on_429_raises_rate_limit_error(handler_scripted: Any) -> None:
    """Exhausting retries on 429 still maps through RateLimitError, not APIError."""
    handler, request_count, _sleeps = handler_scripted([429, 429, 429, 429])

    with pytest.raises(RateLimitError):
        await handler.get("UserStories", 1)

    assert request_count() == 4


async def test_no_retry_on_4xx_other_than_429(handler_scripted: Any) -> None:
    """A non-429 4xx is never retried."""
    handler, request_count, sleeps = handler_scripted([404])

    with pytest.raises(NotFoundError):
        await handler.get("UserStories", 1)

    assert request_count() == 1
    assert sleeps == []


async def test_post_5xx_never_retried(handler_scripted: Any) -> None:
    """A 5xx on a mutating request (POST) raises immediately - it may already be committed."""
    handler, request_count, sleeps = handler_scripted([500])

    with pytest.raises(APIError):
        await handler.create("UserStories", {"Name": "New Story"})

    assert request_count() == 1
    assert sleeps == []


async def test_post_429_never_retried(handler_scripted: Any) -> None:
    """A 429 on a mutating request (POST) raises immediately, not retried.

    TargetProcess documents no guarantee that a 429 means the mutation was
    not processed, and offers no idempotency keys - so mutating methods
    never auto-retry, on 429 or 5xx alike.
    """
    handler, request_count, sleeps = handler_scripted([429], retry_after={429: "0"})

    with pytest.raises(RateLimitError):
        await handler.create("UserStories", {"Name": "New Story"})

    assert request_count() == 1
    assert sleeps == []


async def test_retry_after_malformed_falls_back_to_exponential(handler_scripted: Any) -> None:
    """A Retry-After that is neither numeric seconds nor an HTTP-date falls back to backoff."""
    handler, request_count, sleeps = handler_scripted(
        [429, 200], retry_after={429: "not-a-valid-retry-after-value"}
    )

    await handler.get("UserStories", 1)

    assert request_count() == 2
    assert sleeps == [0.5]


async def test_retry_after_http_date_yields_clamped_positive_delay(handler_scripted: Any) -> None:
    """An HTTP-date Retry-After a few seconds ahead is honoured, not exponential-fallback.

    The HTTP-date is 10s out (well past the 0.5s exponential-fallback
    delay), and the lower assertion bound is set above 0.5s, so this test
    can only pass if the HTTP-date branch actually ran - a test that merely
    asserted ``0 < sleeps[0] <= 30.0`` would also be satisfied by the
    exponential fallback and so wouldn't discriminate between the two
    branches.
    """
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=10))
    handler, request_count, sleeps = handler_scripted([429, 200], retry_after={429: future})

    await handler.get("UserStories", 1)

    assert request_count() == 2
    assert 0.5 < sleeps[0] <= 30.0


async def test_retry_delay_capped_at_thirty_seconds(handler_scripted: Any) -> None:
    """A large Retry-After is capped at 30s rather than honoured verbatim."""
    handler, _request_count, sleeps = handler_scripted([429, 200], retry_after={429: "9999"})

    await handler.get("UserStories", 1)

    assert sleeps == [30.0]


async def test_retry_delay_floored_at_zero_for_negative_retry_after(
    handler_scripted: Any,
) -> None:
    """A negative Retry-After is floored at 0s rather than passed through."""
    handler, _request_count, sleeps = handler_scripted([429, 200], retry_after={429: "-5"})

    await handler.get("UserStories", 1)

    assert sleeps == [0.0]


async def test_network_error_not_retried(handler_with_connect_error: RequestHandler) -> None:
    """A transport-level failure (no response received) is never retried."""
    with pytest.raises(NetworkError):
        await handler_with_connect_error.get("UserStories", 1)


async def test_rate_limiter_applies_per_attempt(handler_scripted: Any) -> None:
    """The rate limiter is (re-)acquired on every attempt, not once per call."""

    class _CountingLimiter:
        def __init__(self) -> None:
            self.enter_count = 0

        async def __aenter__(self) -> "_CountingLimiter":
            self.enter_count += 1
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    handler, request_count, _sleeps = handler_scripted([429, 500, 200])
    counting_limiter = _CountingLimiter()
    handler._rate_limiter = counting_limiter  # type: ignore[assignment]

    await handler.get("UserStories", 1)

    assert counting_limiter.enter_count == request_count() == 3


async def test_rate_limiter_does_not_block_loop(handler_with_response: Any) -> None:
    """The rate limiter must use the async context manager, not a blocking sync one.

    A limiter double that raises if the sync __enter__ is ever invoked
    proves the non-blocking property deterministically - no wall-clock
    timing involved, so this can never flake under CI scheduling jitter.
    """

    class _AsyncOnlyLimiter:
        async def __aenter__(self) -> "_AsyncOnlyLimiter":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        def __enter__(self) -> None:
            raise AssertionError("sync acquire must not be used - blocks the event loop")

        def __exit__(self, *args: object) -> None:
            pass

    handler = handler_with_response({"Id": 1})
    handler._rate_limiter = _AsyncOnlyLimiter()  # type: ignore[assignment]

    await asyncio.gather(handler.get("UserStories", 1), handler.get("UserStories", 2))


async def test_download_file_hits_instance_root_and_returns_bytes() -> None:
    """download_file GETs the instance root, not /api/v1, and returns raw bytes."""
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=b"file-bytes")

    handler = _handler_with_mock_transport(handle)

    result = await handler.download_file("/Attachment.aspx?AttachmentID=1234")

    assert result == b"file-bytes"
    assert len(captured) == 1
    url = captured[0].url
    assert url.host == "example.tpondemand.com"
    assert url.path == "/Attachment.aspx"
    assert "/api/v1" not in url.path
    assert url.params["AttachmentID"] == "1234"
    # The transport's auth still applies - the token is merged in at send time.
    assert url.params["access_token"] == "secret-token"


async def test_download_file_rejects_redirect() -> None:
    """A 3xx on download raises instead of returning the redirect's empty body."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "/login.aspx"})

    handler = _handler_with_mock_transport(handle)

    with pytest.raises(APIError) as exc_info:
        await handler.download_file("/Attachment.aspx?AttachmentID=1")

    assert exc_info.value.status_code == 302


async def test_download_file_maps_error_status() -> None:
    """Error statuses on download map through the normal exception table."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"Message": "no such attachment"})

    handler = _handler_with_mock_transport(handle)

    with pytest.raises(NotFoundError):
        await handler.download_file("/Attachment.aspx?AttachmentID=1")


async def test_upload_file_sends_multipart_and_returns_text() -> None:
    """upload_file POSTs multipart/form-data to the instance root, text back."""
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text="raw-upload-response")

    handler = _handler_with_mock_transport(handle)

    result = await handler.upload_file(
        "/UploadFile.ashx",
        data={"generalid": "42"},
        files={"file": ("image.png", b"png-bytes", "image/png")},
    )

    assert result == "raw-upload-response"
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.host == "example.tpondemand.com"
    assert request.url.path == "/UploadFile.ashx"
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    body = request.read()
    assert b'name="generalid"' in body and b"42" in body
    assert b'name="file"' in body and b'filename="image.png"' in body
    assert b"png-bytes" in body


async def test_upload_file_rejects_redirect() -> None:
    """A 3xx on upload raises - the file was not accepted."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "/login.aspx"})

    handler = _handler_with_mock_transport(handle)

    with pytest.raises(APIError) as exc_info:
        await handler.upload_file(
            "/UploadFile.ashx", data={"generalid": "1"}, files={"file": ("f", b"x")}
        )

    assert exc_info.value.status_code == 302


async def test_upload_file_write_gated() -> None:
    """upload_file consults check_write before sending anything."""
    requests_sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests_sent.append(request)
        return httpx.Response(200, text="")

    def refuse() -> None:
        raise ReadOnlyViolation()

    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    transport._client._transport = httpx.MockTransport(handle)
    handler = RequestHandler(transport, check_write=refuse)

    with pytest.raises(ReadOnlyViolation):
        await handler.upload_file(
            "/UploadFile.ashx", data={"generalid": "1"}, files={"file": ("f", b"x")}
        )

    assert requests_sent == []


@pytest.mark.parametrize(
    "bad_path",
    [
        "@attacker.example/file",  # domain becomes userinfo; host = attacker
        ".attacker.example/file",  # slash-less prefix extends the hostname
        "Attachment.aspx?AttachmentID=1",  # relative - same class as above
        "//attacker.example/file",  # protocol-relative host swap
        "",  # no path at all
    ],
)
async def test_download_file_rejects_host_reanchoring_path(bad_path: str) -> None:
    """A path without exactly one leading slash is refused before any request.

    download_file's path can come from a server-supplied Attachment ``Uri``,
    and interpolated after the domain a malformed value re-anchors the URL's
    host - sending the request, credential included, to a host the caller
    never chose.
    """
    requests_sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests_sent.append(request)
        return httpx.Response(200, content=b"")

    handler = _handler_with_mock_transport(handle)

    with pytest.raises(ValueError, match="exactly one leading '/'"):
        await handler.download_file(bad_path)

    assert requests_sent == []


@pytest.mark.parametrize(
    "bad_path",
    ["@attacker.example/upload", "UploadFile.ashx", "//attacker.example/upload"],
)
async def test_upload_file_rejects_host_reanchoring_path(bad_path: str) -> None:
    """upload_file enforces the same instance-root path constraint."""
    requests_sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests_sent.append(request)
        return httpx.Response(200, text="")

    handler = _handler_with_mock_transport(handle)

    with pytest.raises(ValueError, match="exactly one leading '/'"):
        await handler.upload_file(bad_path, data={"generalid": "1"}, files={"file": ("f", b"x")})

    assert requests_sent == []


@pytest.mark.parametrize(
    "bad_type",
    [
        "UserStories/57731",  # path segment: turns a create into an update of 57731
        "RelationTypes/",  # trailing slash: slips past a name-keyed guard
        " RelationType",  # leading whitespace: same
        "UserStories?take=1",  # query injection
        "User'Story",  # filter injection (shared with priorities.for_entity_type)
        "",  # no name at all
    ],
)
async def test_entity_methods_reject_malformed_entity_type(bad_type: str) -> None:
    """Every entity method refuses a non-identifier entity type before any request.

    ``entity_type`` is interpolated straight into the request path, and the
    generic resource takes it from the caller at runtime, so anything beyond
    a plain identifier would re-shape the request - enforced here at the
    handler, the same way ``_require_instance_path`` guards file paths.
    """
    requests_sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests_sent.append(request)
        return httpx.Response(200, json={"Items": [], "Next": None})

    handler = _handler_with_mock_transport(handle)
    match = "entity_type must be a TP entity type name"

    with pytest.raises(ValueError, match=match):
        await handler.get(bad_type, 1)
    with pytest.raises(ValueError, match=match):
        async for _ in handler.list(bad_type):
            pass
    with pytest.raises(ValueError, match=match):
        await handler.create(bad_type, {"Name": "x"})
    with pytest.raises(ValueError, match=match):
        await handler.update(bad_type, 1, {"Name": "x"})
    with pytest.raises(ValueError, match=match):
        await handler.delete(bad_type, 1)
    with pytest.raises(ValueError, match=match):
        await handler.bulk(bad_type, [{"Name": "x"}])

    assert requests_sent == []
