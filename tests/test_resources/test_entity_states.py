"""Tests for EntityStatesResource."""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess_py.client import TargetProcessClient
from targetprocess_py.exceptions import AmbiguousMatchError, NotFoundError
from targetprocess_py.models import EntityState
from targetprocess_py.request_handler import RequestHandler
from targetprocess_py.resources.entity_states import EntityStatesResource
from targetprocess_py.types import ClientMode
from tests._support.request_handler import scripted_list


@pytest.mark.asyncio
async def test_entity_states_resource_entity_type():
    """Test EntityStatesResource has correct entity_type."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = EntityStatesResource(mock_client, mock_request_handler)

    assert resource.entity_type == "EntityState"
    assert resource.model_class == EntityState


@pytest.mark.asyncio
async def test_entity_states_inherits_crud():
    """Test EntityStatesResource inherits CRUD operations."""
    mock_client = Mock()
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock()

    resource = EntityStatesResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")


# --- workflow-scoped lookups ----------------------------------------------------------------

_WORKFLOW = {"ResourceType": "Workflow", "Id": 7, "Name": "Example workflow"}

# In API order, which is deliberately not Id order: the two final states arrive
# as 54 then 53, so a helper that sorted would be caught.
WORKFLOW_STATES: list[dict[str, Any]] = [
    {
        "ResourceType": "EntityState",
        "Id": 51,
        "Name": "Open",
        "IsInitial": True,
        "IsFinal": False,
        "NumericPriority": 1.0,
        "Workflow": _WORKFLOW,
    },
    {
        "ResourceType": "EntityState",
        "Id": 54,
        "Name": "Rejected",
        "IsInitial": False,
        "IsFinal": True,
        "NumericPriority": 4.0,
        "Workflow": _WORKFLOW,
    },
    {
        "ResourceType": "EntityState",
        "Id": 52,
        "Name": "In Progress",
        "IsInitial": False,
        "IsFinal": False,
        "NumericPriority": 2.0,
        "Workflow": _WORKFLOW,
    },
    {
        "ResourceType": "EntityState",
        "Id": 53,
        "Name": "Done",
        "IsInitial": False,
        "IsFinal": True,
        "NumericPriority": 3.0,
        "Workflow": _WORKFLOW,
    },
]

_STATE_FIELDS = [
    "Id",
    "Name",
    "IsFinal",
    "IsInitial",
    "IsCommentRequired",
    "NumericPriority",
    "Workflow",
    "Role",
]


def _resource(records: list[dict[str, Any]]) -> tuple[EntityStatesResource, dict[str, Any]]:
    """Build a resource whose handler yields ``records`` and records what it was asked."""
    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READONLY
    handler = Mock(spec=RequestHandler)
    handler.list, seen = scripted_list(records)
    return EntityStatesResource(client, handler), seen


async def test_for_workflow_filters_on_the_workflow_and_asks_for_the_state_fields():
    resource, seen = _resource(WORKFLOW_STATES)

    states = await resource.for_workflow(7)

    assert seen["entity_type"] == "EntityState"
    assert seen["where"] == "Workflow.Id eq 7"
    assert seen["include"] == _STATE_FIELDS
    assert seen["limit"] is None
    assert [s.id for s in states] == [51, 54, 52, 53]
    assert all(s.workflow is not None and s.workflow.id == 7 for s in states)


@pytest.mark.parametrize("workflow_id", ["7 or 1 eq 1", True, 7.9, "7", None])
async def test_for_workflow_refuses_a_workflow_id_that_is_not_an_integer(workflow_id: Any):
    resource, seen = _resource(WORKFLOW_STATES)

    with pytest.raises(ValueError, match="workflow_id"):
        await resource.for_workflow(workflow_id)

    assert seen == {}


async def test_resolve_returns_the_single_match_within_the_workflow():
    resource, seen = _resource(WORKFLOW_STATES)

    state = await resource.resolve("Done", workflow_id=7)

    assert seen["where"] == "Workflow.Id eq 7"
    assert state.id == 53
    assert state.is_final is True


async def test_resolve_is_case_insensitive():
    resource, _ = _resource(WORKFLOW_STATES)

    state = await resource.resolve("in progress", workflow_id=7)

    assert state.id == 52


async def test_resolve_lists_the_workflows_names_when_absent():
    resource, _ = _resource(WORKFLOW_STATES)

    with pytest.raises(NotFoundError) as excinfo:
        await resource.resolve("Shipped", workflow_id=7)

    message = str(excinfo.value)
    assert "workflow 7" in message
    assert "'Shipped'" in message
    assert "available: Done, In Progress, Open, Rejected" in message


async def test_resolve_refuses_to_guess_between_duplicates():
    duplicates = [WORKFLOW_STATES[3], {**WORKFLOW_STATES[3], "Id": 99}]
    resource, _ = _resource(duplicates)

    with pytest.raises(AmbiguousMatchError) as excinfo:
        await resource.resolve("Done", workflow_id=7)

    assert "Ids: 53, 99" in str(excinfo.value)


async def test_final_states_returns_the_final_members_in_api_order():
    resource, seen = _resource(WORKFLOW_STATES)

    final = await resource.final_states(7)

    assert seen["where"] == "Workflow.Id eq 7"
    assert [s.id for s in final] == [54, 53]
    assert all(s.is_final is True for s in final)


async def test_final_states_is_empty_when_the_workflow_has_none():
    resource, _ = _resource([s for s in WORKFLOW_STATES if not s["IsFinal"]])

    assert await resource.final_states(7) == []


async def test_client_exposes_entity_states_lazily():
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="t", mode=ClientMode.READONLY
    )
    try:
        first = client.entity_states
        assert isinstance(first, EntityStatesResource)
        assert client.entity_states is first
    finally:
        await client.aclose()
