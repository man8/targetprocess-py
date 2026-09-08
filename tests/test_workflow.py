"""Tests for Workflow model."""

from targetprocess.models import Workflow


def test_workflow_full_parsing() -> None:
    workflow = Workflow.model_validate(
        {
            "Id": 73,
            "ResourceType": "Workflow",
            "Name": "Project workflow",
            "Process": {"ResourceType": "Process", "Id": 2, "Name": "Scrum"},
            "EntityType": {"ResourceType": "EntityType", "Id": 8, "Name": "Bug"},
            "ParentWorkflow": {"ResourceType": "Workflow", "Id": 70, "Name": "Root"},
        }
    )
    assert workflow.id == 73
    assert workflow.name == "Project workflow"
    assert workflow.process is not None and workflow.process.name == "Scrum"
    assert workflow.entity_type is not None and workflow.entity_type.id == 8
    assert workflow.parent_workflow is not None and workflow.parent_workflow.id == 70
    assert workflow.model_extra == {}


def test_workflow_entity_type_reference_parses_without_an_id() -> None:
    # TP does not identify an EntityType reference uniformly (see
    # EntityTypeRef); a partial one must not fail the whole workflow.
    workflow = Workflow.model_validate(
        {"Id": 74, "Name": "Sub", "EntityType": {"ResourceType": "EntityType"}}
    )
    assert workflow.entity_type is not None
    assert workflow.entity_type.id is None
    assert workflow.entity_type.name is None


def test_workflow_minimal_parsing() -> None:
    workflow = Workflow.model_validate({"Id": 1, "Name": "W"})
    assert workflow.process is None
    assert workflow.parent_workflow is None
