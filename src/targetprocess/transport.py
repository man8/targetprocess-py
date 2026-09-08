"""HTTP transport layer for TargetProcess API."""

from collections.abc import Generator
from typing import Any

import httpx

from targetprocess._observability import (
    REQUEST_ID_HEADER,
    current_request_id,
    new_request_id,
)


async def _stamp_request_id(request: httpx.Request) -> None:
    """Stamp the correlation ID header on an outgoing request.

    Uses the ID bound to the current context when one is set (so a caller's
    request context flows end-to-end), otherwise generates a fresh one so
    every outgoing request is still traceable. A caller-supplied header is
    never overwritten.
    """
    if REQUEST_ID_HEADER in request.headers:
        return
    request.headers[REQUEST_ID_HEADER] = current_request_id() or new_request_id()


class _QueryTokenAuth(httpx.Auth):
    """Injects the TP token as an access_token query param at send time.

    Merges into whatever query the request URL already carries — TP accepts
    tokens only as a query parameter, and client-level params would replace
    embedded query strings instead of merging.
    """

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.url = request.url.copy_merge_params({"access_token": self._token})
        yield request


class HTTPTransport:
    """HTTP transport for TargetProcess API.

    Handles:
    - Base URL construction
    - Authentication (access_token query param, or Basic auth header)
    - Connection pooling
    - Timeout configuration
    """

    def __init__(
        self,
        domain: str,
        token: str | None = None,
        *,
        basic_auth: tuple[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        """Initialize HTTP transport.

        Args:
            domain: TargetProcess domain (e.g., 'example.tpondemand.com')
            token: API authentication token, sent as the `access_token` query
                parameter (TP's only header-less token scheme).
            basic_auth: (username, password) tuple, sent as an `Authorization:
                Basic` header. Mutually exclusive with `token`.
            timeout: Custom timeout configuration (default: 5s connect, 30s read)

        Raises:
            ValueError: If neither or both of `token`/`basic_auth` are provided.
        """
        if (token is None) == (basic_auth is None):
            raise ValueError("Provide exactly one of token or basic_auth")

        self.domain = domain
        self.base_url = f"https://{domain}/api/v1"

        if timeout is None:
            timeout = httpx.Timeout(5.0, connect=5.0, read=30.0)

        # TP's API accepts tokens ONLY as a query parameter (access_token=);
        # there is no header-borne token scheme. Basic auth is the sole
        # header alternative and requires real user credentials. The token is
        # injected via a custom Auth (applied at send time) rather than
        # client-level `params=`, because httpx client-level params REPLACE
        # any query string already embedded in a request URL instead of
        # merging with it.
        auth: httpx.Auth
        if token is not None:
            auth = _QueryTokenAuth(token)
        else:
            assert basic_auth is not None
            auth = httpx.BasicAuth(*basic_auth)

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=timeout,
            event_hooks={"request": [_stamp_request_id]},
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "HTTPTransport":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        await self.close()
