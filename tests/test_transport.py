"""Tests for HTTP transport layer."""

import httpx
import pytest

from targetprocess.transport import HTTPTransport


def _install_mock_transport(transport: HTTPTransport, handler: httpx.MockTransport) -> None:
    """Swap the real network transport for a MockTransport on the send path.

    HTTPTransport doesn't expose a way to inject `transport=` into the
    underlying httpx.AsyncClient at construction time, so the least invasive
    way to capture what the client actually sends (after auth_flow has run)
    is to replace the already-constructed client's private `_transport`.
    """
    transport._client._transport = handler


async def test_token_sent_as_access_token_query_param_relative_url_with_embedded_query() -> None:
    """Relative URL with an embedded query string (RequestHandler's own shape)."""
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    _install_mock_transport(transport, httpx.MockTransport(handle))

    await transport._client.request("GET", "/UserStories?format=json&take=5")

    sent = captured[0]
    assert sent.url.params["access_token"] == "secret-token"
    assert sent.url.params["format"] == "json"
    assert sent.url.params["take"] == "5"


async def test_token_sent_as_access_token_query_param_with_params_kwarg() -> None:
    """Relative URL plus a `params=` kwarg."""
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    _install_mock_transport(transport, httpx.MockTransport(handle))

    await transport._client.request("GET", "/UserStories", params={"take": "5"})

    sent = captured[0]
    assert sent.url.params["access_token"] == "secret-token"
    assert sent.url.params["take"] == "5"


async def test_token_sent_as_access_token_query_param_absolute_next_url() -> None:
    """Absolute URL with an embedded query string (the server-provided `Next` shape)."""
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    _install_mock_transport(transport, httpx.MockTransport(handle))

    await transport._client.request(
        "GET", "https://example.tpondemand.com/api/v1/UserStories?skip=25"
    )

    sent = captured[0]
    assert sent.url.params["access_token"] == "secret-token"
    assert sent.url.params["skip"] == "25"


async def test_basic_auth_sent_as_authorization_header() -> None:
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    transport = HTTPTransport(domain="example.tpondemand.com", basic_auth=("john", "pw"))
    _install_mock_transport(transport, httpx.MockTransport(handle))

    assert isinstance(transport._client.auth, httpx.BasicAuth)

    await transport._client.request("GET", "/UserStories")

    sent = captured[0]
    assert "access_token" not in sent.url.params
    assert sent.headers["authorization"].startswith("Basic ")


def test_token_and_basic_auth_mutually_exclusive() -> None:
    with pytest.raises(ValueError):
        HTTPTransport(domain="x.tpondemand.com", token="t", basic_auth=("u", "p"))
    with pytest.raises(ValueError):
        HTTPTransport(domain="x.tpondemand.com")


def test_token_absent_from_repr() -> None:
    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    assert "secret-token" not in repr(transport)
    assert "secret-token" not in repr(transport._client)
