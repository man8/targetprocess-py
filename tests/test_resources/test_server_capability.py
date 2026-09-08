"""Tests for the server-declared write surface on the typed resources.

Each collection's ``/meta`` reports ``CanCreate`` / ``CanUpdate`` /
``CanDelete``; a typed resource declares that surface on its class and refuses
the missing operations before any request is sent, in every client mode. This
module pins that per resource, and pins the ordinary READONLY-mode refusal on
every manager added in the same change. Write behaviour is exercised against
doubles only - no live write is ever probed.
"""

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from targetprocess import ClientMode, ReadOnlyViolation, RequestHandler, TargetProcessClient
from targetprocess.resources.base import BaseResource
from targetprocess.resources.custom_rules import CustomRulesResource
from targetprocess.resources.entity_types import EntityTypesResource
from targetprocess.resources.relation_types import RelationTypesResource
from targetprocess.resources.terms import TermsResource

# Every write on the shared surface, keyed by the operation each maps to.
WRITES: dict[str, tuple[str, Callable[[Any], Awaitable[Any]]]] = {
    "create": ("create", lambda r: r.create(Name="x")),
    "update": ("update", lambda r: r.update(1, Name="x")),
    "delete": ("delete", lambda r: r.delete(1)),
    "create_many": ("create", lambda r: r.create_many([{"Name": "x"}])),
    "update_many": ("update", lambda r: r.update_many([{"Id": 1}])),
}

SERVER_READ_ONLY = [RelationTypesResource, EntityTypesResource, TermsResource]

NEW_ACCESSORS = [
    "team_iterations",
    "custom_fields",
    "severities",
    "processes",
    "workflows",
    "entity_types",
    "terms",
    "custom_activities",
    "custom_rules",
]


def _readwrite_doubles() -> tuple[Mock, AsyncMock]:
    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READWRITE
    return client, AsyncMock(spec=RequestHandler)


def _assert_nothing_sent(client: Mock, handler: AsyncMock) -> None:
    client._check_write_permission.assert_not_called()
    for method in ("create", "update", "delete", "bulk"):
        getattr(handler, method).assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_cls", SERVER_READ_ONLY, ids=lambda c: c.__name__)
@pytest.mark.parametrize("write", list(WRITES), ids=list(WRITES))
async def test_server_read_only_collection_refuses_every_write_in_readwrite_mode(
    resource_cls: type[BaseResource[Any]], write: str
):
    """The refusal precedes the mode gate and the wire - mode never comes into it."""
    client, handler = _readwrite_doubles()
    resource = resource_cls(client, handler)
    _, call = WRITES[write]

    with pytest.raises(ReadOnlyViolation, match="read-only on the server") as excinfo:
        await call(resource)

    assert excinfo.value.resource == resource_cls.entity_type
    _assert_nothing_sent(client, handler)


@pytest.mark.asyncio
@pytest.mark.parametrize("write", ["create", "delete", "create_many"])
async def test_custom_rules_refuse_the_operations_the_server_lacks(write: str):
    """CustomRules: CanCreate and CanDelete are false, so those - and only those - are refused."""
    client, handler = _readwrite_doubles()
    resource = CustomRulesResource(client, handler)
    operation, call = WRITES[write]

    with pytest.raises(ReadOnlyViolation, match=f"does not accept {operation} on the server"):
        await call(resource)

    _assert_nothing_sent(client, handler)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("write", "handler_method"), [("update", "update"), ("update_many", "bulk")]
)
async def test_custom_rules_accept_update_under_the_ordinary_gate(write: str, handler_method: str):
    """CustomRules: CanUpdate is true, so update reaches the handler once the mode gate passes."""
    client, handler = _readwrite_doubles()
    handler.update.return_value = {"Id": 1, "ResourceType": "CustomRule", "IsEnabled": True}
    handler.bulk.return_value = [{"Id": 1, "ResourceType": "CustomRule", "IsEnabled": True}]
    resource = CustomRulesResource(client, handler)
    _, call = WRITES[write]

    await call(resource)

    client._check_write_permission.assert_called_once()
    getattr(handler, handler_method).assert_called_once()
    for other in {"create", "update", "delete", "bulk"} - {handler_method}:
        getattr(handler, other).assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("accessor", NEW_ACCESSORS)
async def test_new_resources_writes_blocked_in_readonly_mode(accessor: str):
    """The full write path raises ReadOnlyViolation on a READONLY client, before the wire.

    On the server-restricted collections the refusal fires for the server
    reason first; either way nothing may reach the transport.
    """
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="test-token", mode=ClientMode.READONLY
    )

    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"guard did not fire: {request.method} {request.url.path}")

    client._transport._client._transport = httpx.MockTransport(handle)
    resource = getattr(client, accessor)

    for _, call in WRITES.values():
        with pytest.raises(ReadOnlyViolation):
            await call(resource)
