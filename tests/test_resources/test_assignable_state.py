"""Tests for the two entity-state levels of an assignable: reading them and advancing them.

Each scenario runs a real client over an ``httpx.MockTransport`` answering from a
small in-memory instance: one story, its team assignments, and two workflows -
the project workflow 5 (states 51, 52, 53) and a team workflow 9 (61, 62, 63).
Writes change the instance, so a read after a write shows what the write did,
and the story or a team assignment can be told to ignore its writes to stand in
for a transition TargetProcess accepted and did not apply.
"""

import json
from typing import Any

import httpx
import pytest

from targetprocess_py import TargetProcessClient
from targetprocess_py.exceptions import (
    AmbiguousMatchError,
    NotFoundError,
    ParseError,
    ReadOnlyViolation,
    SplitTransitionError,
    VerificationError,
)
from targetprocess_py.models import EntityState
from targetprocess_py.resources.assignables import AssignableResource
from targetprocess_py.resources.base import ASSIGNABLE_IGNORED_FILTER_PATHS
from targetprocess_py.resources.bugs import BugsResource
from targetprocess_py.resources.epics import EpicsResource
from targetprocess_py.resources.features import FeaturesResource
from targetprocess_py.resources.requests import RequestsResource
from targetprocess_py.resources.tasks import TasksResource
from targetprocess_py.resources.user_stories import UserStoriesResource
from targetprocess_py.types import ClientMode, LevelState, StateLevels

_PROJECT_WORKFLOW = 5
_TEAM_WORKFLOW = 9

# state Id -> (name, workflow Id, final)
_STATES: dict[int, tuple[str, int, bool]] = {
    51: ("Open", _PROJECT_WORKFLOW, False),
    52: ("In Progress", _PROJECT_WORKFLOW, False),
    53: ("Done", _PROJECT_WORKFLOW, True),
    61: ("Planned", _TEAM_WORKFLOW, False),
    62: ("Develop", _TEAM_WORKFLOW, False),
    63: ("Released", _TEAM_WORKFLOW, True),
}

_STORY = "/api/v1/UserStory/123"
_TEAM_ASSIGNMENT = "/api/v1/TeamAssignment/700"


def _reference(state_id: int) -> dict[str, Any]:
    return {
        "ResourceType": "EntityState",
        "Id": state_id,
        "Name": _STATES[state_id][0],
        "NumericPriority": float(state_id),
    }


def _state(state_id: int) -> dict[str, Any]:
    name, workflow_id, final = _STATES[state_id]
    return {
        "ResourceType": "EntityState",
        "Id": state_id,
        "Name": name,
        "IsFinal": final,
        "IsInitial": False,
        "IsCommentRequired": False,
        "NumericPriority": float(state_id),
        "Workflow": {"ResourceType": "Workflow", "Id": workflow_id, "Name": "Example workflow"},
        "Role": None,
    }


class _Instance:
    """An in-memory instance answering the routes the two-level helpers use.

    ``team_states`` holds one state Id per team assignment (Ids 700, 701, ...).
    With ``mirrors_item`` the first assignment has no state of its own and
    reads back the item's - the collapsed case, where both levels are one
    state object. With ``item_ignores_writes`` a story write, and with
    ``team_ignores_writes`` a team-assignment write, echoes the requested state
    and leaves the stored one unchanged.
    """

    def __init__(
        self,
        *,
        item_state: int = 51,
        team_states: tuple[int, ...] = (61,),
        mirrors_item: bool = False,
        item_ignores_writes: bool = False,
        team_ignores_writes: bool = False,
    ) -> None:
        self.item_state = item_state
        self.team_states = {700 + n: state for n, state in enumerate(team_states)}
        self.mirrors_item = mirrors_item
        self.item_ignores_writes = item_ignores_writes
        self.team_ignores_writes = team_ignores_writes
        self.log: list[httpx.Request] = []

    def client(self, mode: ClientMode = ClientMode.READWRITE) -> TargetProcessClient:
        client = TargetProcessClient(domain="example.tpondemand.com", token="test-token", mode=mode)
        client._transport._client._transport = httpx.MockTransport(self._handle)
        return client

    def posts(self) -> list[tuple[str, dict[str, Any]]]:
        return [(r.url.path, json.loads(r.content)) for r in self.log if r.method == "POST"]

    def gets(self, path: str) -> int:
        return sum(1 for r in self.log if r.method == "GET" and r.url.path == path)

    def _team_state(self, assignment_id: int) -> int:
        return self.item_state if self.mirrors_item else self.team_states[assignment_id]

    def _assignment(self, assignment_id: int) -> dict[str, Any]:
        return {
            "ResourceType": "TeamAssignment",
            "Id": assignment_id,
            "Team": {"ResourceType": "Team", "Id": 32, "Name": "Example team"},
            "Assignable": {"ResourceType": "Assignable", "Id": 123, "Name": "Example"},
            "EntityState": _reference(self._team_state(assignment_id)),
        }

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.log.append(request)
        body = self._answer(request)
        if body is None:
            raise AssertionError(f"unexpected request {request.method} {request.url}")
        return httpx.Response(200, json=body)

    def _answer(self, request: httpx.Request) -> dict[str, Any] | None:
        path, where = request.url.path, request.url.params.get("where")
        if path == _STORY:
            state = self.item_state
            if request.method == "POST":
                state = json.loads(request.content)["EntityState"]["Id"]
                if not self.item_ignores_writes:
                    self.item_state = state
            return {"ResourceType": "UserStory", "Id": 123, "EntityState": _reference(state)}
        if path == "/api/v1/EntityState":
            workflow_id = int(str(where).removeprefix("Workflow.Id eq "))
            ids = [s for s, (_, workflow, _) in _STATES.items() if workflow == workflow_id]
            return {"Items": [_state(state_id) for state_id in ids]}
        if path.startswith("/api/v1/EntityState/"):
            return _state(int(path.rsplit("/", 1)[1]))
        if path == "/api/v1/TeamAssignment":
            assert where == "Assignable.Id eq 123"
            return {"Items": [self._assignment(n) for n in self.team_states]}
        if path.startswith("/api/v1/TeamAssignment/"):
            return self._team_assignment(request, int(path.rsplit("/", 1)[1]))
        return None

    def _team_assignment(self, request: httpx.Request, assignment_id: int) -> dict[str, Any]:
        if request.method != "POST":
            return self._assignment(assignment_id)
        requested = json.loads(request.content)["EntityState"]["Id"]
        if not self.team_ignores_writes:
            self.team_states[assignment_id] = requested
        return {**self._assignment(assignment_id), "EntityState": _reference(requested)}


def _state_model(state_id: int) -> EntityState:
    return EntityState.model_validate(_state(state_id))


# --- entity_state_levels --------------------------------------------------------------------


async def test_levels_with_no_team_assignment_have_no_team_level() -> None:
    instance = _Instance(team_states=())

    levels = await instance.client().user_stories.entity_state_levels(123)

    assert levels == StateLevels(
        project=LevelState(state_id=51, state_name="Open", workflow_id=_PROJECT_WORKFLOW),
        team=None,
        team_assignment_id=None,
        collapsed=False,
    )


async def test_levels_in_two_workflows_are_distinct() -> None:
    instance = _Instance(item_state=52, team_states=(62,))

    levels = await instance.client().user_stories.entity_state_levels(123)

    assert levels == StateLevels(
        project=LevelState(state_id=52, state_name="In Progress", workflow_id=_PROJECT_WORKFLOW),
        team=LevelState(state_id=62, state_name="Develop", workflow_id=_TEAM_WORKFLOW),
        team_assignment_id=700,
        collapsed=False,
    )
    team_listing = next(r for r in instance.log if r.url.path == "/api/v1/TeamAssignment")
    assert team_listing.url.params["include"] == "[EntityState,Team]"


async def test_levels_sharing_one_state_object_are_collapsed_with_one_state_read() -> None:
    instance = _Instance(item_state=52, team_states=(52,), mirrors_item=True)

    levels = await instance.client().user_stories.entity_state_levels(123)

    assert levels.collapsed is True
    assert levels.team == levels.project
    assert levels.team_assignment_id == 700
    assert instance.gets("/api/v1/EntityState/52") == 1


async def test_levels_refuse_an_item_with_several_team_assignments() -> None:
    instance = _Instance(team_states=(61, 62))

    with pytest.raises(AmbiguousMatchError) as caught:
        await instance.client().user_stories.entity_state_levels(123)

    assert caught.value.count == 2
    assert caught.value.assignable_id == 123
    assert "team_assignments.update" in str(caught.value)


# --- advance_state: the distinct case -------------------------------------------------------


async def test_advance_writes_the_item_then_the_team_and_returns_both_levels() -> None:
    instance = _Instance()

    moved = await instance.client().user_stories.advance_state(123, to=53, team_to=63)

    assert instance.posts() == [
        (_STORY, {"EntityState": {"Id": 53}}),
        (_TEAM_ASSIGNMENT, {"EntityState": {"Id": 63}}),
    ]
    assert moved == StateLevels(
        project=LevelState(state_id=53, state_name="Done", workflow_id=_PROJECT_WORKFLOW),
        team=LevelState(state_id=63, state_name="Released", workflow_id=_TEAM_WORKFLOW),
        team_assignment_id=700,
        collapsed=False,
    )
    # verify=True by default: each written level is re-read independently.
    assert instance.gets(_TEAM_ASSIGNMENT) == 1


async def test_advance_without_team_to_refuses_a_split_before_any_write() -> None:
    instance = _Instance()

    with pytest.raises(SplitTransitionError) as caught:
        await instance.client().user_stories.advance_state(123, to=53)

    error = caught.value
    assert (error.entity_id, error.project_workflow_id, error.team_workflow_id) == (123, 5, 9)
    assert "workflow 9" in str(error)
    assert instance.posts() == []


async def test_advance_resolves_each_target_by_name_within_its_own_workflow() -> None:
    instance = _Instance()

    await instance.client().user_stories.advance_state(123, to="done", team_to="Released")

    assert instance.posts() == [
        (_STORY, {"EntityState": {"Id": 53}}),
        (_TEAM_ASSIGNMENT, {"EntityState": {"Id": 63}}),
    ]


async def test_advance_does_not_resolve_a_team_state_name_in_the_project_workflow() -> None:
    instance = _Instance()

    with pytest.raises(NotFoundError, match="workflow 5"):
        await instance.client().user_stories.advance_state(123, to="Released", team_to=63)

    assert instance.posts() == []


async def test_advance_refuses_a_state_id_outside_the_levels_workflow() -> None:
    instance = _Instance()

    with pytest.raises(NotFoundError, match="team workflow 9"):
        await instance.client().user_stories.advance_state(123, to=53, team_to=53)

    assert instance.posts() == []


async def test_advance_takes_entity_state_targets_from_their_own_workflow() -> None:
    instance = _Instance()

    await instance.client().user_stories.advance_state(
        123, to=_state_model(52), team_to=_state_model(62)
    )

    assert [body for _, body in instance.posts()] == [
        {"EntityState": {"Id": 52}},
        {"EntityState": {"Id": 62}},
    ]


async def test_advance_refuses_an_entity_state_from_another_workflow() -> None:
    instance = _Instance()

    with pytest.raises(ValueError, match="project workflow 5"):
        await instance.client().user_stories.advance_state(123, to=_state_model(62), team_to=63)

    assert instance.posts() == []


async def test_advance_refuses_a_target_that_is_not_a_state_id_name_or_record() -> None:
    instance = _Instance()

    with pytest.raises(TypeError):
        await instance.client().user_stories.advance_state(123, to=True, team_to=63)

    assert instance.posts() == []


async def test_advance_raises_when_the_team_level_did_not_move() -> None:
    instance = _Instance(team_ignores_writes=True)

    with pytest.raises(VerificationError) as caught:
        await instance.client().user_stories.advance_state(123, to=53, team_to=63)

    assert caught.value.entity_type == "TeamAssignment"
    assert caught.value.entity_id == 700
    assert instance.item_state == 53  # the item moved; the error reports the level that did not


async def test_advance_raises_before_the_team_write_when_the_item_did_not_move() -> None:
    instance = _Instance(item_ignores_writes=True)

    with pytest.raises(VerificationError) as caught:
        await instance.client().user_stories.advance_state(123, to=53, team_to=63)

    assert caught.value.entity_type == "UserStory"
    assert caught.value.entity_id == 123
    # The item's re-read raised before the team write was sent, so neither level moved.
    assert instance.posts() == [(_STORY, {"EntityState": {"Id": 53}})]
    assert instance.item_state == 51
    assert instance.team_states == {700: 61}


async def test_advance_unverified_reads_both_levels_back() -> None:
    instance = _Instance(team_ignores_writes=True)

    moved = await instance.client().user_stories.advance_state(123, to=53, team_to=63, verify=False)

    assert moved.project.state_id == 53
    assert moved.team is not None and moved.team.state_id == 61  # what was read, not what was sent
    assert instance.gets(_STORY) == 2  # the levels read before the writes, and after


# --- advance_state: the collapsed case ------------------------------------------------------


async def test_advance_collapsed_is_one_write() -> None:
    instance = _Instance(item_state=51, team_states=(51,), mirrors_item=True)

    moved = await instance.client().user_stories.advance_state(123, to=53)

    assert instance.posts() == [(_STORY, {"EntityState": {"Id": 53}})]
    assert moved.collapsed is True
    assert (
        moved.project
        == moved.team
        == LevelState(state_id=53, state_name="Done", workflow_id=_PROJECT_WORKFLOW)
    )
    # The team level is re-read too, as the evidence it followed the item.
    assert instance.gets(_TEAM_ASSIGNMENT) == 1


async def test_advance_collapsed_unverified_sends_one_write_and_reads_the_levels_back() -> None:
    instance = _Instance(item_state=51, team_states=(51,), mirrors_item=True)

    moved = await instance.client().user_stories.advance_state(123, to=53, verify=False)

    assert instance.posts() == [(_STORY, {"EntityState": {"Id": 53}})]
    assert instance.gets(_TEAM_ASSIGNMENT) == 0
    assert moved.collapsed is True
    assert moved.team is not None and moved.team.state_id == 53


async def test_advance_collapsed_accepts_an_agreeing_team_to() -> None:
    instance = _Instance(item_state=51, team_states=(51,), mirrors_item=True)

    await instance.client().user_stories.advance_state(123, to=53, team_to="Done")

    assert instance.posts() == [(_STORY, {"EntityState": {"Id": 53}})]


async def test_advance_collapsed_refuses_a_different_team_to() -> None:
    instance = _Instance(item_state=51, team_states=(51,), mirrors_item=True)

    with pytest.raises(SplitTransitionError) as caught:
        await instance.client().user_stories.advance_state(123, to=53, team_to=52)

    assert caught.value.project_workflow_id == caught.value.team_workflow_id == 5
    assert instance.posts() == []


async def test_advance_collapsed_raises_when_the_team_level_did_not_follow() -> None:
    instance = _Instance(item_state=51, team_states=(51,), mirrors_item=False)

    with pytest.raises(VerificationError) as caught:
        await instance.client().user_stories.advance_state(123, to=53)

    assert caught.value.entity_type == "TeamAssignment"
    assert caught.value.mismatches[700]["EntityState"][0] == {"Id": 53}


# --- advance_state: no team level, and the write gate ---------------------------------------


async def test_advance_with_no_team_level_is_one_write() -> None:
    instance = _Instance(team_states=())

    moved = await instance.client().user_stories.advance_state(123, to=52)

    assert instance.posts() == [(_STORY, {"EntityState": {"Id": 52}})]
    assert moved.team is None and moved.collapsed is False


async def test_advance_with_no_team_level_refuses_team_to() -> None:
    instance = _Instance(team_states=())

    with pytest.raises(ValueError, match="no team assignment"):
        await instance.client().user_stories.advance_state(123, to=52, team_to=62)

    assert instance.posts() == []


async def test_advance_on_a_readonly_client_reads_and_writes_nothing() -> None:
    instance = _Instance()

    with pytest.raises(ReadOnlyViolation):
        await instance.client(ClientMode.READONLY).user_stories.advance_state(
            123, to=53, team_to=63
        )

    assert instance.gets(_STORY) == 1  # the levels were read
    assert instance.posts() == []


def test_a_record_read_without_its_state_or_workflow_is_refused() -> None:
    from targetprocess_py.resources.assignables import _level, _state_ref

    with pytest.raises(ParseError, match="UserStory 123 was read without its EntityState"):
        _state_ref(None, owner="UserStory 123")
    with pytest.raises(ParseError, match="EntityState 51 was read without its Workflow"):
        _level(EntityState.model_validate({**_state(51), "Workflow": None}))


# --- the six assignable managers ------------------------------------------------------------


@pytest.mark.parametrize(
    "resource_cls",
    [
        UserStoriesResource,
        BugsResource,
        TasksResource,
        FeaturesResource,
        EpicsResource,
        RequestsResource,
    ],
)
def test_every_assignable_manager_is_an_assignable_resource(resource_cls: type[Any]) -> None:
    assert issubclass(resource_cls, AssignableResource)
    assert resource_cls.ignored_filter_paths is ASSIGNABLE_IGNORED_FILTER_PATHS
