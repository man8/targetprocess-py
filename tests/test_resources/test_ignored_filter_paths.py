"""Tests for the refusal of where= paths TargetProcess accepts and silently ignores.

A filter on the Assignments collection of an assignable answers HTTP 200 with the
unfiltered rows, so the assignable managers and the generic entities path refuse
it before any request. Names added with the refusal are imported inside each
test, so that against a library without it each test fails on its own assertion
rather than at collection.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from targetprocess import resources
from targetprocess.client import TargetProcessClient
from targetprocess.models import UserStory
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.base import BaseResource
from targetprocess.resources.bugs import BugsResource
from targetprocess.resources.entities import EntitiesResource, _spellings
from targetprocess.resources.epics import EpicsResource
from targetprocess.resources.features import FeaturesResource
from targetprocess.resources.requests import RequestsResource
from targetprocess.resources.tasks import TasksResource
from targetprocess.resources.user_stories import UserStoriesResource
from targetprocess.types import ClientMode
from tests._support.request_handler import scripted_list

# Each assignable manager, with the collection (plural) name TP addresses it by.
ASSIGNABLE_COLLECTIONS: dict[type[BaseResource[Any]], str] = {
    UserStoriesResource: "UserStories",
    BugsResource: "Bugs",
    TasksResource: "Tasks",
    FeaturesResource: "Features",
    EpicsResource: "Epics",
    RequestsResource: "Requests",
}

# The Assignable-derived collections with no typed manager, so reachable only
# through the generic accessor: the collection name TP addresses, mapped to the
# singular entity type it is declared as. The four beyond Assignable were each
# confirmed live against an unfiltered control on the same collection.
UNTYPED_ASSIGNABLE_COLLECTIONS: dict[str, str] = {
    "Assignables": "Assignable",
    "PortfolioEpics": "PortfolioEpic",
    "TestPlanRuns": "TestPlanRun",
    "InboundAssignables": "InboundAssignable",
    "OutboundAssignables": "OutboundAssignable",
}
IGNORED_WHERE = "Assignments.GeneralUser.Id eq 1"


class _CollidingResource(BaseResource[UserStory]):
    entity_type = "UserStory"
    model_class = UserStory
    ignored_filter_paths = {"Comments": "use client.comments instead"}


class _PlainResource(BaseResource[UserStory]):
    entity_type = "UserStory"
    model_class = UserStory


def _resource(resource_cls: type[BaseResource[Any]]) -> tuple[BaseResource[Any], AsyncMock]:
    handler = AsyncMock(spec=RequestHandler)
    return resource_cls(Mock(spec=TargetProcessClient), handler), handler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "where",
    ["Comments.Id eq 1", "(comments.Owner.Id eq 2)", "(Project.Id eq 2) and (COMMENTS.Id gt 0)"],
)
async def test_declared_filter_path_is_refused_before_any_request(where: str):
    """A declared path is refused by its leading segment, in any casing, before the handler."""
    resource, handler = _resource(_CollidingResource)

    with pytest.raises(ValueError, match="use client.comments instead") as excinfo:
        async for _ in resource.list(where=where):
            pass
    assert f"where={where!r} is not supported on UserStory" in str(excinfo.value)
    handler.list.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "where",
    [
        None,
        "CommentsCount gt 0",
        "LastComments.Id eq 1",
        "Comment.Id eq 1",
        "Owner.Comments.Id eq 1",
        "Name contains 'Comments.txt'",
        'Description contains "see Comments.Id"',
    ],
)
async def test_undeclared_filter_path_is_forwarded_verbatim(where: str | None):
    """A name that is not the leading segment of a declared path reaches the handler unchanged."""
    resource, handler = _resource(_CollidingResource)
    handler.list, seen = scripted_list([{"Id": 1, "ResourceType": "UserStory", "Name": "Story"}])

    assert [story.id async for story in resource.list(where=where)] == [1]
    assert seen["where"] == where


def test_a_resource_declaring_nothing_accepts_every_filter():
    """A resource with no ignored paths refuses nothing - the common case."""
    assert _PlainResource.ignored_filter_paths == {}
    _PlainResource.check_where(None)
    _PlainResource.check_where(IGNORED_WHERE)


def test_check_filter_paths_matches_the_leading_segment_only():
    """Any casing of the leading segment is refused, Assignments.Count included; nothing else."""
    from targetprocess.resources.base import ASSIGNABLE_IGNORED_FILTER_PATHS, check_filter_paths

    refused = (
        "Assignments.Count gt 0",
        "assignments.Role.Name eq 'QA'",
        "Id gt 0 and ASSIGNMENTS.Id gt 0",
    )
    for where in refused:
        with pytest.raises(ValueError, match="is not supported on Bugs"):
            check_filter_paths(where, ASSIGNABLE_IGNORED_FILTER_PATHS, resource="Bugs")
    passed = (
        "TeamAssignments.Team.Id eq 1",
        "Assignment.Id eq 1",
        "Owner.Assignments.Id eq 1",
        "Name contains 'Assignments.cs'",
        "(Name eq 'x') and (Description contains 'Assignments.GeneralUser')",
    )
    for where in (*passed, "AssignedUser.Id eq 1", ""):
        check_filter_paths(where, ASSIGNABLE_IGNORED_FILTER_PATHS, resource="Bugs")
    check_filter_paths(IGNORED_WHERE, {}, resource="Bugs")


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_cls", list(ASSIGNABLE_COLLECTIONS), ids=lambda c: c.__name__)
async def test_assignable_managers_refuse_a_filter_on_assignments(
    resource_cls: type[BaseResource[Any]],
):
    """Every assignable manager refuses the ignored filter, naming the join-entity route."""
    resource, handler = _resource(resource_cls)

    with pytest.raises(ValueError, match="client.assignments") as excinfo:
        async for _ in resource.list(where="(Assignments.GeneralUser.Id eq 7)"):
            pass
    message = str(excinfo.value)
    assert f"is not supported on {resource_cls.entity_type}" in message
    assert "GeneralUser.Id" in message
    handler.list.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_cls", list(ASSIGNABLE_COLLECTIONS), ids=lambda c: c.__name__)
async def test_assignable_managers_forward_a_valid_filter_unchanged(
    resource_cls: type[BaseResource[Any]],
):
    """A filter on the assignable's own fields reaches the handler exactly as written."""
    where = "(EntityState.IsFinal eq 'false') and (AssignedUser.Id eq 7)"
    resource, handler = _resource(resource_cls)
    handler.list, seen = scripted_list([])

    assert [item async for item in resource.list(where=where)] == []
    assert seen["where"] == where


def test_the_known_set_is_declared_once_and_shared():
    """The six managers reference one declaration, whose only entry is Assignments."""
    from targetprocess.resources.base import ASSIGNABLE_IGNORED_FILTER_PATHS

    assert set(ASSIGNABLE_IGNORED_FILTER_PATHS) == {"Assignments"}
    assert "client.assignments" in ASSIGNABLE_IGNORED_FILTER_PATHS["Assignments"]
    for resource_cls in ASSIGNABLE_COLLECTIONS:
        assert resource_cls.ignored_filter_paths is ASSIGNABLE_IGNORED_FILTER_PATHS, resource_cls


def test_the_reason_states_both_observed_failure_shapes():
    """One message covers both: a field filter is ignored, Assignments.Count is rejected.

    The prefix is refused whole because no path under it filters, but the two
    shapes fail differently, and a caller who wrote either should read
    something true. Pinned here so neither half can be dropped silently.
    """
    from targetprocess.resources.base import ASSIGNABLE_IGNORED_FILTER_PATHS

    reason = ASSIGNABLE_IGNORED_FILTER_PATHS["Assignments"]
    assert "ignored" in reason and "HTTP 200" in reason
    assert "Assignments.Count" in reason and "HTTP 400" in reason
    assert "client.assignments" in reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_type",
    [
        "UserStory",
        "userstories",
        "Bugs",
        "Task",
        "Features",
        "EPIC",
        "Requests",
        "Assignable",
        "Assignables",
    ],
)
async def test_entities_refuse_the_filter_for_every_assignable_spelling(entity_type: str):
    """The generic path refuses it too, reporting the spelling the caller passed."""
    handler = AsyncMock(spec=RequestHandler)
    entities = EntitiesResource(Mock(spec=TargetProcessClient), handler)

    with pytest.raises(ValueError, match="client.assignments") as excinfo:
        async for _ in entities.list(entity_type, where=IGNORED_WHERE):
            pass
    assert f"is not supported on {entity_type}:" in str(excinfo.value)
    handler.list.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_type",
    [
        spelling
        for collection, singular in UNTYPED_ASSIGNABLE_COLLECTIONS.items()
        for spelling in (collection, singular)
    ],
)
async def test_untyped_assignable_collections_refuse_a_filter_on_assignments(entity_type: str):
    """Each Assignable-derived collection without a typed manager refuses it too.

    These have no resource class to carry the declaration, so the generic
    accessor's map is the only place the refusal can live - and the only route
    a caller has to them. Both spellings TP accepts are covered.
    """
    handler = AsyncMock(spec=RequestHandler)
    entities = EntitiesResource(Mock(spec=TargetProcessClient), handler)

    with pytest.raises(ValueError, match="client.assignments") as excinfo:
        async for _ in entities.list(entity_type, where=IGNORED_WHERE):
            pass
    assert f"is not supported on {entity_type}:" in str(excinfo.value)
    handler.list.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_type", sorted(UNTYPED_ASSIGNABLE_COLLECTIONS))
async def test_untyped_assignable_collections_forward_a_valid_filter_unchanged(entity_type: str):
    """Only the Assignments prefix is refused on them; their own fields pass through."""
    where = "(EntityState.IsFinal eq 'false') and (AssignedUser.Id eq 7)"
    handler = AsyncMock(spec=RequestHandler)
    handler.list, seen = scripted_list([])
    entities = EntitiesResource(Mock(spec=TargetProcessClient), handler)

    assert [item async for item in entities.list(entity_type, where=where)] == []
    assert (seen["entity_type"], seen["where"]) == (entity_type, where)


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_type", ["Comment", "Project"])
async def test_entities_forward_the_filter_where_nothing_is_declared(entity_type: str):
    """Collections with no declaration receive the same filter untouched."""
    handler = AsyncMock(spec=RequestHandler)
    handler.list, seen = scripted_list([])
    entities = EntitiesResource(Mock(spec=TargetProcessClient), handler)

    assert [item async for item in entities.list(entity_type, where=IGNORED_WHERE)] == []
    assert (seen["entity_type"], seen["where"]) == (entity_type, IGNORED_WHERE)


def test_every_manager_with_ignored_filter_paths_is_mirrored_on_the_generic_path():
    """The generic map reaches each declaring manager, and each untyped collection.

    Two dimensions, and they are independent: the *paths* refused (one,
    ``Assignments``) and the *collections* the refusal is applied to. Widening
    coverage to a collection adds spellings here and no path there.
    """
    from targetprocess.resources.assignables import AssignableResource
    from targetprocess.resources.base import ASSIGNABLE_IGNORED_FILTER_PATHS
    from targetprocess.resources.entities import (
        _IGNORED_FILTER_PATHS,
        _UNTYPED_ASSIGNABLE_COLLECTIONS,
    )

    # AssignableResource declares the set once for the six managers; it is their
    # base class rather than a manager, so it has no collection to mirror.
    declaring = {
        candidate
        for candidate in (getattr(resources, name) for name in resources.__all__)
        if isinstance(candidate, type)
        and issubclass(candidate, BaseResource)
        and candidate is not AssignableResource
        and candidate.ignored_filter_paths
    }
    assert declaring == set(ASSIGNABLE_COLLECTIONS)

    for resource_cls, collection in ASSIGNABLE_COLLECTIONS.items():
        for spelling in {*_spellings(resource_cls.entity_type), collection, collection.upper()}:
            reached = _IGNORED_FILTER_PATHS.get(spelling.casefold())
            assert reached is resource_cls.ignored_filter_paths, spelling
    # The untyped collections this suite names are exactly the ones the module
    # declares, so the two cannot drift apart unnoticed.
    assert set(_UNTYPED_ASSIGNABLE_COLLECTIONS) == set(UNTYPED_ASSIGNABLE_COLLECTIONS.values())

    for singular in UNTYPED_ASSIGNABLE_COLLECTIONS.values():
        for spelling in {*_spellings(singular), singular.upper()}:
            reached = _IGNORED_FILTER_PATHS.get(spelling.casefold())
            assert reached is ASSIGNABLE_IGNORED_FILTER_PATHS, spelling

    declared_spellings = frozenset().union(
        *(_spellings(cls.entity_type) for cls in ASSIGNABLE_COLLECTIONS),
        *(_spellings(singular) for singular in UNTYPED_ASSIGNABLE_COLLECTIONS.values()),
    )
    assert set(_IGNORED_FILTER_PATHS) <= declared_spellings


@pytest.mark.asyncio
async def test_a_real_client_refuses_before_the_transport_is_reached():
    """Through a READONLY client, the typed and generic surfaces both refuse pre-request."""
    client = TargetProcessClient(domain="example.invalid", token="unused", mode=ClientMode.READONLY)
    sent: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        raise AssertionError("the ignored filter reached the transport")

    client._transport._client._transport = httpx.MockTransport(record)

    with pytest.raises(ValueError, match="client.assignments"):
        async for _ in client.user_stories.list(where=IGNORED_WHERE):
            pass
    with pytest.raises(ValueError, match="client.assignments"):
        async for _ in client.entities.list("Assignables", where=IGNORED_WHERE):
            pass
    assert sent == []
