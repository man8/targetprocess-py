"""Tests for Process model."""

from targetprocess.models import Process


def test_process_full_parsing() -> None:
    process = Process.model_validate(
        {
            "Id": 2,
            "ResourceType": "Process",
            "Name": "Scrum",
            "Description": "Sample process description",
            "IsDefault": True,
        }
    )
    assert process.id == 2
    assert process.name == "Scrum"
    assert process.description == "Sample process description"
    assert process.is_default is True
    assert process.model_extra == {}


def test_process_minimal_parsing() -> None:
    process = Process.model_validate({"Id": 3, "Name": "Kanban"})
    assert process.description is None
    assert process.is_default is None


def test_process_preserves_undeclared_fields() -> None:
    process = Process.model_validate({"Id": 3, "Name": "Kanban", "SomeFutureField": "kept"})
    assert process.model_extra is not None
    assert process.model_extra["SomeFutureField"] == "kept"
