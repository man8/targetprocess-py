"""Tests for WorkflowsResource."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import ClientMode, RequestHandler, TargetProcessClient
from targetprocess.models import Workflow
from targetprocess.resources.workflows import WorkflowsResource
from tests._support.request_handler import scripted_list


def test_workflows_resource_entity_type():
    resource = WorkflowsResource(Mock(spec=TargetProcessClient), AsyncMock(spec=RequestHandler))
    assert resource.entity_type == "Workflow"
    assert resource.model_class == Workflow
    # /meta: CanCreate, CanUpdate and CanDelete all true.
    assert all(WorkflowsResource.server_permits(op) for op in ("create", "update", "delete"))
    # Names repeat per process, so no instance-wide resolver is offered.
    assert not hasattr(resource, "resolve")


@pytest.mark.asyncio
async def test_workflows_list_parses_scope_references():
    """list() yields workflows with their process, entity-type and parent references."""
    _list, seen = scripted_list(
        [
            {
                "Id": 73,
                "ResourceType": "Workflow",
                "Name": "Sample workflow",
                "Process": {"ResourceType": "Process", "Id": 2, "Name": "Scrum"},
                "EntityType": {"ResourceType": "EntityType", "Id": 8, "Name": "Bug"},
                "ParentWorkflow": None,
            },
            {
                "Id": 74,
                "ResourceType": "Workflow",
                "Name": "Sample sub-workflow",
                "Process": {"ResourceType": "Process", "Id": 2, "Name": "Scrum"},
                "EntityType": {"ResourceType": "EntityType"},
                "ParentWorkflow": {"ResourceType": "Workflow", "Id": 73, "Name": "Sample workflow"},
            },
        ]
    )
    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READONLY
    handler = Mock(spec=RequestHandler)
    handler.list = _list
    resource = WorkflowsResource(client, handler)

    root, sub = [w async for w in resource.list(where="Process.Id eq 2")]

    assert seen["where"] == "Process.Id eq 2"
    assert root.parent_workflow is None
    assert root.entity_type is not None and root.entity_type.name == "Bug"
    assert sub.parent_workflow is not None and sub.parent_workflow.id == root.id
    # A partially identified EntityType reference does not fail the record.
    assert sub.entity_type is not None and sub.entity_type.id is None
