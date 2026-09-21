"""Tests for the verified TeamIteration clear on the work-item managers.

TargetProcess cascades a parent's team iteration onto its children, so a
child's explicit null is answered with a success status whether it cleared or
not. ``clear_team_iteration`` sends the clear and checks it, through the same
verified-write path as any other checked write. Each scenario runs a real client
over an ``httpx.MockTransport`` whose write echo deliberately differs from the
re-read, so a test can tell which of the two the method returned.

Names added with the clear are imported inside each test, so that against a
library without it each test fails on its own assertion rather than at
collection.
"""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from targetprocess_py import TargetProcessClient
from targetprocess_py.exceptions import ReadOnlyViolation, VerificationError
from targetprocess_py.types import ClientMode

_STORY = "/api/v1/UserStory/123"
_PARENT_ITERATION = {"Id": 77, "Name": "Sanitised Name", "ResourceType": "TeamIteration"}

Responder = dict[str, Any] | Callable[[httpx.Request], dict[str, Any]]


def _client(
    routes: dict[tuple[str, str], Responder], *, mode: ClientMode = ClientMode.READWRITE
) -> tuple[TargetProcessClient, list[httpx.Request]]:
    """A client whose transport answers ``routes`` by method and path, logging each request."""
    log: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        log.append(request)
        route = routes.get((request.method, request.url.path))
        if route is None:
            raise AssertionError(f"unexpected request {request.method} {request.url.path}")
        body = route(request) if callable(route) else route
        return httpx.Response(200, json=body)

    client = TargetProcessClient(domain="example.tpondemand.com", token="test-token", mode=mode)
    client._transport._client._transport = httpx.MockTransport(handle)
    return client, log


def _story(**fields: Any) -> dict[str, Any]:
    return {"ResourceType": "UserStory", "Id": 123, **fields}


async def test_a_clear_that_lands_posts_a_null_then_reads_it_back() -> None:
    """One write, one narrowed re-read, and the re-read is what comes back."""
    client, log = _client(
        {
            # The echo still carries the iteration - TP's response to a write can
            # be stale, which is the reason this method does not read it.
            ("POST", _STORY): _story(TeamIteration=_PARENT_ITERATION),
            ("GET", _STORY): _story(TeamIteration=None),
        }
    )

    story = await client.user_stories.clear_team_iteration(123)

    assert [request.method for request in log] == ["POST", "GET"]
    assert json.loads(log[0].content) == {"TeamIteration": None}
    assert log[1].url.params["include"] == "[TeamIteration]"
    assert story.id == 123
    assert story.team_iteration is None


async def test_a_clear_the_cascade_discards_raises_the_named_error() -> None:
    """A success status and a field still set: the error names the cascade and the value."""
    from targetprocess_py.exceptions import TeamIterationCascadeError

    client, log = _client(
        {
            # The echo says the clear worked. The independent re-read is what
            # shows it did not - this is the whole failure this method exists for.
            ("POST", _STORY): _story(TeamIteration=None),
            ("GET", _STORY): _story(TeamIteration=_PARENT_ITERATION),
        }
    )

    with pytest.raises(TeamIterationCascadeError) as caught:
        await client.user_stories.clear_team_iteration(123)

    error = caught.value
    assert [request.method for request in log] == ["POST", "GET"]
    assert error.entity_type == "UserStory"
    assert error.entity_id == 123
    assert error.mismatches == {123: {"TeamIteration": (None, _PARENT_ITERATION)}}
    assert error.verified_ids == []
    message = str(error)
    assert "UserStory 123 still carries a TeamIteration after the clear" in message
    assert "77" in message
    assert "cascades a parent's team iteration" in message
    assert "clear or detach the parent" in message


async def test_the_named_error_is_a_verification_error() -> None:
    """A caller handling the general failure catches the cascade too."""
    from targetprocess_py.exceptions import TeamIterationCascadeError

    assert issubclass(TeamIterationCascadeError, VerificationError)

    client, _ = _client(
        {
            ("POST", _STORY): _story(),
            ("GET", _STORY): _story(TeamIteration=_PARENT_ITERATION),
        }
    )

    with pytest.raises(VerificationError):
        await client.user_stories.clear_team_iteration(123)


async def test_the_named_error_is_exported_from_the_package_root() -> None:
    """The type a caller catches is part of the public surface."""
    import targetprocess_py
    from targetprocess_py.exceptions import TeamIterationCascadeError

    assert targetprocess_py.TeamIterationCascadeError is TeamIterationCascadeError
    assert "TeamIterationCascadeError" in targetprocess_py.__all__


async def test_a_reread_that_omits_the_field_counts_as_cleared() -> None:
    """An absent key satisfies a requested None, as it does for any verified write."""
    client, log = _client(
        {
            ("POST", _STORY): _story(TeamIteration=_PARENT_ITERATION),
            ("GET", _STORY): _story(),
        }
    )

    story = await client.user_stories.clear_team_iteration(123)

    assert [request.method for request in log] == ["POST", "GET"]
    assert story.team_iteration is None


async def test_clearing_an_item_that_had_none_verifies() -> None:
    """The call is idempotent: nothing to clear still reads back clear."""
    client, log = _client(
        {
            ("POST", _STORY): _story(TeamIteration=None),
            ("GET", _STORY): _story(TeamIteration=None),
        }
    )

    assert (await client.user_stories.clear_team_iteration(123)).team_iteration is None
    assert [request.method for request in log] == ["POST", "GET"]


async def test_a_readonly_client_sends_nothing() -> None:
    """The mode gate runs before the write, as it does for every other mutation."""
    client, log = _client({}, mode=ClientMode.READONLY)

    with pytest.raises(ReadOnlyViolation):
        await client.user_stories.clear_team_iteration(123)

    assert log == []


@pytest.mark.parametrize(
    ("accessor", "entity_type", "path"),
    [
        ("user_stories", "UserStory", "/api/v1/UserStory/123"),
        ("bugs", "Bug", "/api/v1/Bug/123"),
        ("tasks", "Task", "/api/v1/Task/123"),
        ("features", "Feature", "/api/v1/Feature/123"),
        ("epics", "Epic", "/api/v1/Epic/123"),
        ("requests", "Request", "/api/v1/Request/123"),
    ],
)
async def test_every_work_item_manager_carries_the_clear(
    accessor: str, entity_type: str, path: str
) -> None:
    """The method is on the shared base, so all six managers have it, each naming itself."""
    from targetprocess_py.exceptions import TeamIterationCascadeError

    client, _ = _client(
        {
            ("POST", path): {"ResourceType": entity_type, "Id": 123},
            ("GET", path): {
                "ResourceType": entity_type,
                "Id": 123,
                "TeamIteration": _PARENT_ITERATION,
            },
        }
    )

    with pytest.raises(TeamIterationCascadeError) as caught:
        await getattr(client, accessor).clear_team_iteration(123)

    assert caught.value.entity_type == entity_type
    assert f"{entity_type} 123 still carries a TeamIteration" in str(caught.value)


async def test_the_error_survives_a_pickle_round_trip() -> None:
    """Shipping the failure across a process keeps its type, message and mismatches."""
    import pickle

    from targetprocess_py.exceptions import TeamIterationCascadeError

    client, _ = _client(
        {
            ("POST", _STORY): _story(),
            ("GET", _STORY): _story(TeamIteration=_PARENT_ITERATION),
        }
    )

    with pytest.raises(TeamIterationCascadeError) as caught:
        await client.user_stories.clear_team_iteration(123)

    loaded = pickle.loads(pickle.dumps(caught.value))

    assert type(loaded) is TeamIterationCascadeError
    assert str(loaded) == str(caught.value)
    assert loaded.entity_type == "UserStory"
    assert loaded.entity_id == 123
    assert loaded.mismatches == {123: {"TeamIteration": (None, _PARENT_ITERATION)}}


async def test_the_clear_is_the_shared_verified_write_path() -> None:
    """Not a second mechanism: the request pair is exactly update(verify=True)'s.

    Pinned because the alternative - a bespoke write-then-read inside the
    method - would look identical from the outside until the verified-write
    rules changed underneath it and this one did not follow.
    """
    routes: dict[tuple[str, str], Responder] = {
        ("POST", _STORY): _story(TeamIteration=_PARENT_ITERATION),
        ("GET", _STORY): _story(TeamIteration=None),
    }

    client, via_clear = _client(routes)
    await client.user_stories.clear_team_iteration(123)

    client, via_update = _client(routes)
    await client.user_stories.update(123, TeamIteration=None, verify=True)

    assert [(r.method, r.url.path, r.url.params.multi_items()) for r in via_clear] == [
        (r.method, r.url.path, r.url.params.multi_items()) for r in via_update
    ]
    assert [r.content for r in via_clear] == [r.content for r in via_update]
