"""RequestHandler doubles: a real handler over an httpx.MockTransport, and a list() stand-in."""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import httpx

from targetprocess.request_handler import RequestHandler
from targetprocess.transport import HTTPTransport


def handler_with_mock_transport(
    handle: Any, *, sleep: Callable[[float], Awaitable[None]] | None = None
) -> RequestHandler:
    """Build a real RequestHandler backed by an httpx.MockTransport.

    Routes requests through the real HTTPTransport (auth, base_url, param
    merging all genuinely exercised) rather than mocking
    ``transport._client.request`` directly - needed to prove URL/param
    behaviour like Next-URL query preservation and access_token injection.

    ``sleep`` is passed straight through to RequestHandler so retry-backoff
    tests never really sleep.
    """
    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    transport._client._transport = httpx.MockTransport(handle)
    return RequestHandler(transport, sleep=sleep)


def scripted_list(
    records: Sequence[dict[str, Any]],
) -> tuple[Callable[..., AsyncIterator[dict[str, Any]]], dict[str, Any]]:
    """Return a stand-in for ``RequestHandler.list`` that yields ``records``.

    Declares the real method's keyword-only signature rather than ``**kwargs``,
    so an argument the handler does not accept fails here instead of being
    swallowed by the fake. The returned dict records the entity type and every
    keyword the resource passed, for assertions on what was forwarded.
    """
    seen: dict[str, Any] = {}

    async def _list(
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
    ) -> AsyncIterator[dict[str, Any]]:
        seen.update(
            entity_type=entity_type,
            where=where,
            include=include,
            exclude=exclude,
            result_include=result_include,
            append=append,
            innertake=innertake,
            order_by=order_by,
            order_by_desc=order_by_desc,
            skip=skip,
            limit=limit,
            page_size=page_size,
        )
        for record in records:
            yield record

    return _list, seen
