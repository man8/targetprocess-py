"""Tests for Bug model."""

import pytest
from pydantic import ValidationError

from targetprocess.models import Bug


def test_bug_full_parsing() -> None:
    """Test Bug parses complete API JSON."""
    data = {
        "Id": 456,
        "Name": "Login crashes",
        "ResourceType": "Bug",
        "Severity": {"ResourceType": "Severity", "Id": 3, "Name": "Critical", "Importance": 1},
        "Priority": {"ResourceType": "Priority", "Id": 2, "Name": "Urgent", "Importance": 1},
        "EntityState": {"Id": 1, "Name": "Open"},
        "Project": {"Id": 42, "Name": "Project X"},
        "AssignedUser": {"Items": [{"ResourceType": "User", "Id": 99, "FullName": "John Doe"}]},
        "Team": {"Id": 10, "Name": "Dev Team"},
        "Description": "Application crashes when user tries to login",
        "CreateDate": None,
        "ModifyDate": None,
    }

    bug = Bug.model_validate(data)

    # Base fields
    assert bug.id == 456
    assert bug.name == "Login crashes"
    assert bug.resource_type == "Bug"

    # Bug-specific
    assert bug.severity is not None and bug.severity.name == "Critical"
    assert bug.priority is not None and bug.priority.name == "Urgent"
    assert bug.description == "Application crashes when user tries to login"

    # Relationships
    assert bug.entity_state is not None and bug.entity_state.id == 1
    assert bug.project is not None and bug.project.name == "Project X"
    assert bug.assigned_user is not None
    assert bug.assigned_user[0].id == 99
    assert bug.assigned_user[0].full_name == "John Doe"
    assert bug.team is not None and bug.team.name == "Dev Team"


def test_bug_minimal_parsing() -> None:
    """Test Bug with minimal required fields."""
    data = {
        "Id": 789,
        "Name": "Minimal Bug",
        "ResourceType": "Bug",
        "CreateDate": None,
        "ModifyDate": None,
    }

    bug = Bug.model_validate(data)
    assert bug.id == 789
    assert bug.severity is None
    assert bug.priority is None
    assert bug.entity_state is None


def test_bug_priority_validation() -> None:
    """Test Bug.priority (a reference object) requires an Id like any other ref."""
    data = {
        "Id": 999,
        "Name": "Invalid Bug",
        "ResourceType": "Bug",
        "Priority": {"ResourceType": "Priority", "Name": "Urgent", "Importance": 1},
        "CreateDate": None,
        "ModifyDate": None,
    }

    with pytest.raises(ValidationError) as exc_info:
        Bug.model_validate(data)

    assert "id" in str(exc_info.value).lower()


def test_bug_severity_priority_are_refs() -> None:
    b = Bug.model_validate(
        {
            "ResourceType": "Bug",
            "Id": 9,
            "Name": "crash",
            "Severity": {"ResourceType": "Severity", "Id": 1, "Name": "Blocking", "Importance": 1},
            "Priority": {"ResourceType": "Priority", "Id": 4, "Name": "Urgent", "Importance": 1},
        }
    )
    assert b.severity is not None and b.severity.name == "Blocking"
    assert b.priority is not None and b.priority.importance == 1


def test_partial_fetch_validates() -> None:
    # include=[Id] style partial payloads must not fail on missing fields
    b = Bug.model_validate({"ResourceType": "Bug", "Id": 9})
    assert b.id == 9 and b.name is None
