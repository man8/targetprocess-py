"""Tests for the request handler's query-parameter allowlist.

TargetProcess answers a query parameter it does not recognise with HTTP 200 and
the unfiltered rows, so every name the handler sends is declared once and any
other name is refused before the request is built. Names added with the
allowlist are imported inside each test, so that against a handler without it
each test fails on its own assertion rather than at collection.
"""

from typing import Any

import httpx
import pytest

from targetprocess.request_handler import RequestHandler
from targetprocess.transport import HTTPTransport


def _capturing(handler_cls: type[RequestHandler]) -> tuple[RequestHandler, list[httpx.Request]]:
    """Build ``handler_cls`` over a MockTransport that records every request it is sent."""
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"Id": 1, "Items": [{"Id": 1}], "Next": None})

    transport = HTTPTransport(domain="example.invalid", token="secret-token")
    transport._client._transport = httpx.MockTransport(handle)
    return handler_cls(transport), captured


def test_query_parameters_pin_exactly_what_the_builders_emit() -> None:
    """The allowlist equals every name the builders emit: no dead entry, no undeclared one."""
    from targetprocess.request_handler import QUERY_PARAMETERS

    shaping: dict[str, Any] = {
        "include": ["Name"],
        "exclude": ["Description"],
        "result_include": ["Id"],
        "append": ["Tasks-Count"],
        "innertake": 3,
    }
    listing: dict[str, Any] = {"where": "Id gt 0", "skip": 5, "limit": 10, "page_size": 25}
    # order_by and order_by_desc together raise, so each direction is built once.
    ascending = RequestHandler._list_params(
        order_by="Name", order_by_desc=None, **listing, **shaping
    )
    descending = RequestHandler._list_params(
        order_by=None, order_by_desc="Id", **listing, **shaping
    )
    emitted = set(ascending) | set(descending) | set(RequestHandler._shaping_params(**shaping))

    assert emitted == QUERY_PARAMETERS


@pytest.mark.parametrize("limit", [None, 0])
async def test_unknown_query_parameter_is_refused_before_any_request_on_list(
    limit: int | None,
) -> None:
    """A built parameter outside the allowlist raises before the wire - even at limit=0."""

    class _SortingHandler(RequestHandler):
        @staticmethod
        def _list_params(**_: Any) -> dict[str, str]:
            return {"format": "json", "take": "25", "sort": "CreateDate"}

    handler, captured = _capturing(_SortingHandler)

    with pytest.raises(ValueError, match=r"\bsort\b"):
        async for _ in handler.list("UserStories", limit=limit):
            pass
    assert captured == []


async def test_unknown_query_parameter_is_refused_before_any_request_on_get() -> None:
    """get() applies the same check to its built parameters before the URL is formed."""

    class _SortingHandler(RequestHandler):
        @staticmethod
        def _shaping_params(**_: Any) -> dict[str, str]:
            return {"sort": "CreateDate"}

    handler, captured = _capturing(_SortingHandler)

    with pytest.raises(ValueError, match=r"\bsort\b"):
        await handler.get("UserStories", 1)
    assert captured == []


async def test_valid_query_reaches_the_wire_unchanged(
    handler_with_capture: tuple[RequestHandler, list[httpx.Request]],
) -> None:
    """Every declared parameter is sent as rendered, and nothing outside the allowlist is."""
    from targetprocess.request_handler import QUERY_PARAMETERS

    handler, captured = handler_with_capture
    where = "(EntityState.IsFinal eq 'false') and (AssignedUser.Id eq 7)"
    async for _ in handler.list(
        "UserStories",
        where=where,
        include=["Name", "EntityState"],
        exclude=["Tags"],
        result_include=["Id", "Name"],
        append=["Bugs-Count"],
        innertake=2,
        order_by="CreateDate",
        skip=5,
    ):
        break

    params = captured[0].url.params
    assert params["where"] == where
    assert params["include"] == "[Name,EntityState]"
    assert params["exclude"] == "[Tags]"
    assert params["resultInclude"] == "[Id,Name]"
    assert params["append"] == "[Bugs-Count]"
    assert params["innertake"] == "2"
    assert params["orderBy"] == "CreateDate"
    assert params["skip"] == "5"
    assert set(params) - {"access_token"} <= QUERY_PARAMETERS
