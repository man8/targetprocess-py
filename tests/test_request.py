"""Tests for Request model."""

from targetprocess.models import Request


def test_request_full_parsing() -> None:
    """Test Request parses complete API JSON."""
    data = {
        "Id": 321,
        "Name": "Add dark mode",
        "ResourceType": "Request",
        "Effort": 8.0,
        "Description": "Users want a dark mode option",
        "EntityState": {"Id": 5, "Name": "Submitted"},
        "Project": {"Id": 42, "Name": "Project X"},
        "AssignedUser": {"Items": [{"ResourceType": "User", "Id": 99, "FullName": "John Doe"}]},
        "Team": {"Id": 10, "Name": "UX Team"},
        "CreateDate": None,
        "ModifyDate": None,
    }

    request = Request.model_validate(data)

    # Base fields
    assert request.id == 321
    assert request.name == "Add dark mode"
    assert request.resource_type == "Request"

    # Request-specific
    assert request.effort == 8.0
    assert request.description == "Users want a dark mode option"

    # Relationships
    assert request.entity_state is not None and request.entity_state.id == 5
    assert request.entity_state.name == "Submitted"
    assert request.project is not None and request.project.name == "Project X"
    assert request.assigned_user is not None
    assert request.assigned_user[0].id == 99
    assert request.team is not None and request.team.name == "UX Team"


def test_request_minimal_parsing() -> None:
    """Test Request with minimal required fields."""
    data = {
        "Id": 654,
        "Name": "Minimal Request",
        "ResourceType": "Request",
        "CreateDate": None,
        "ModifyDate": None,
    }

    request = Request.model_validate(data)
    assert request.id == 654
    assert request.effort is None
    assert request.entity_state is None
