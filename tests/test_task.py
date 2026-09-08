"""Tests for Task model."""

from targetprocess.models import Task


def test_task_full_parsing() -> None:
    """Test Task parses complete API JSON."""
    data = {
        "Id": 789,
        "Name": "Implement login API",
        "ResourceType": "Task",
        "EffortCompleted": 3.5,
        "EffortToDo": 1.5,
        "Description": "Implement OAuth login",
        "EntityState": {"Id": 2, "Name": "In Progress"},
        "Project": {"Id": 42, "Name": "Project X"},
        "AssignedUser": {"Items": [{"ResourceType": "User", "Id": 99, "FullName": "Jane Doe"}]},
        "Team": {"Id": 10, "Name": "Backend Team"},
        "Parent": {"Id": 123, "Name": "User Login"},
        "CreateDate": None,
        "ModifyDate": None,
    }

    task = Task.model_validate(data)

    # Base fields
    assert task.id == 789
    assert task.name == "Implement login API"
    assert task.resource_type == "Task"

    # Task-specific
    assert task.effort_completed == 3.5
    assert task.effort_todo == 1.5
    assert task.description == "Implement OAuth login"

    # Relationships
    assert task.entity_state is not None and task.entity_state.id == 2
    assert task.entity_state.name == "In Progress"
    assert task.project is not None and task.project.name == "Project X"
    assert task.assigned_user is not None
    assert task.assigned_user[0].id == 99
    assert task.team is not None and task.team.name == "Backend Team"
    assert task.parent is not None and task.parent.id == 123


def test_task_minimal_parsing() -> None:
    """Test Task with minimal required fields."""
    data = {
        "Id": 456,
        "Name": "Minimal Task",
        "ResourceType": "Task",
        "CreateDate": None,
        "ModifyDate": None,
    }

    task = Task.model_validate(data)
    assert task.id == 456
    assert task.effort_completed is None
    assert task.effort_todo is None
    assert task.entity_state is None
    assert task.parent is None


def test_task_effort_completed_accepts_whatever_tp_sends() -> None:
    """A server-supplied number carries no range constraint.

    TP computes this and documents no bound. A constraint here would fail the
    whole entity rather than the field, so one odd value would abort an entire
    list() page. Range checks belong on the write side, where the value
    originates - see ``times.upsert``.
    """
    entity = Task.model_validate(
        {"Id": 999, "Name": "Odd but parseable", "ResourceType": "Task", "EffortCompleted": -1.0}
    )
    assert entity.effort_completed == -1.0
    assert entity.name == "Odd but parseable"
