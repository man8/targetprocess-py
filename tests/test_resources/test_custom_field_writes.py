"""Tests for ``set_custom_field``: setting and clearing a custom-field value.

A real client runs over an ``httpx.MockTransport``, so the wire shape a set or
a clear sends is asserted as TargetProcess would receive it, and the re-read
is scripted independently of the write's echo.
"""

import json
from typing import Any

import httpx
import pytest

from targetprocess import TargetProcessClient
from targetprocess.exceptions import ReadOnlyViolation, VerificationError
from targetprocess.types import ClientMode

_STORY = "/api/v1/UserStory/123"


def _client(
    reread: dict[str, Any] | None, *, mode: ClientMode = ClientMode.READWRITE
) -> tuple[TargetProcessClient, list[httpx.Request]]:
    """A client whose write echoes no custom fields and whose re-read answers ``reread``."""
    log: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        log.append(request)
        if request.method == "POST" and request.url.path == _STORY:
            return httpx.Response(200, json={"ResourceType": "UserStory", "Id": 123})
        if request.method == "GET" and request.url.path == _STORY and reread is not None:
            return httpx.Response(200, json=reread)
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    client = TargetProcessClient(domain="example.tpondemand.com", token="test-token", mode=mode)
    client._transport._client._transport = httpx.MockTransport(handle)
    return client, log


def _with_fields(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"ResourceType": "UserStory", "Id": 123, "CustomFields": list(entries)}


async def test_set_sends_the_custom_fields_wire_shape_and_verifies_by_default() -> None:
    client, log = _client(_with_fields({"Name": "Deadline", "Type": "Text", "Value": "2026-10-01"}))

    story = await client.user_stories.set_custom_field(123, "Deadline", "2026-10-01")

    assert [request.method for request in log] == ["POST", "GET"]
    assert json.loads(log[0].content) == {
        "CustomFields": [{"Name": "Deadline", "Value": "2026-10-01"}]
    }
    assert log[1].url.params["include"] == "[CustomFields]"
    # The re-read model, carrying the value read back.
    assert story.custom_fields is not None
    assert [(f.name, f.value) for f in story.custom_fields] == [("Deadline", "2026-10-01")]


async def test_clear_sends_a_null_value() -> None:
    client, log = _client(_with_fields({"Name": "Deadline", "Type": "Text", "Value": None}))

    await client.user_stories.set_custom_field(123, "Deadline", None)

    assert json.loads(log[0].content) == {"CustomFields": [{"Name": "Deadline", "Value": None}]}


@pytest.mark.parametrize("cleared", [None, ""])
async def test_clear_verifies_against_null_or_empty(cleared: str | None) -> None:
    client, _ = _client(_with_fields({"Name": "Deadline", "Type": "Text", "Value": cleared}))

    story = await client.user_stories.set_custom_field(123, "Deadline", None)

    assert story.id == 123


async def test_a_discarded_clear_raises_naming_the_field() -> None:
    client, _ = _client(_with_fields({"Name": "Deadline", "Type": "Text", "Value": "2026-10-01"}))

    with pytest.raises(VerificationError) as caught:
        await client.user_stories.set_custom_field(123, "Deadline", None)

    assert caught.value.mismatches == {123: {"CustomFields[Deadline]": (None, "2026-10-01")}}
    assert "CustomFields[Deadline]: requested None, observed '2026-10-01'" in str(caught.value)


async def test_a_set_that_did_not_land_raises() -> None:
    client, _ = _client(_with_fields({"Name": "Deadline", "Type": "Text", "Value": "2026-09-01"}))

    with pytest.raises(VerificationError) as caught:
        await client.user_stories.set_custom_field(123, "Deadline", "2026-10-01")

    assert caught.value.mismatches == {
        123: {"CustomFields[Deadline]": ("2026-10-01", "2026-09-01")}
    }


async def test_an_entry_absent_from_the_reread_raises() -> None:
    client, _ = _client(_with_fields({"Name": "Other", "Type": "Text", "Value": None}))

    with pytest.raises(VerificationError) as caught:
        await client.user_stories.set_custom_field(123, "Deadlien", None)

    assert caught.value.mismatches == {
        123: {"CustomFields[Deadlien]": (None, VerificationError.ABSENT)}
    }


async def test_the_name_matches_case_insensitively() -> None:
    client, _ = _client(_with_fields({"Name": "Story Points", "Type": "Number", "Value": 3}))

    story = await client.user_stories.set_custom_field(123, "story points", 3.0)

    assert story.id == 123


async def test_verify_false_makes_no_reread_and_returns_the_echo() -> None:
    client, log = _client(None)

    story = await client.user_stories.set_custom_field(123, "Deadline", None, verify=False)

    assert [request.method for request in log] == ["POST"]
    assert story.custom_fields is None


async def test_a_readonly_client_sends_nothing() -> None:
    client, log = _client(None, mode=ClientMode.READONLY)

    with pytest.raises(ReadOnlyViolation):
        await client.user_stories.set_custom_field(123, "Deadline", None)

    assert log == []


async def test_every_typed_manager_has_it() -> None:
    client, _ = _client(None)

    assert callable(client.bugs.set_custom_field)
    assert callable(client.projects.set_custom_field)
