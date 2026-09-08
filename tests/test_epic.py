"""Tests for Epic model."""

from targetprocess.models import Epic


def test_epic_full_parsing() -> None:
    """Test Epic parses complete API JSON."""
    data = {
        "Id": 888,
        "Name": "Security Hardening",
        "ResourceType": "Epic",
        "Effort": 100.0,
        "BusinessValue": 2000,
        "Description": "Security improvements across platform",
        "EntityState": {"Id": 4, "Name": "Active"},
        "Project": {"Id": 42, "Name": "Project X"},
        "Team": {"Id": 10, "Name": "Security Team"},
        "CreateDate": None,
        "ModifyDate": None,
    }

    epic = Epic.model_validate(data)

    # Base fields
    assert epic.id == 888
    assert epic.name == "Security Hardening"
    assert epic.resource_type == "Epic"

    # Epic-specific
    assert epic.effort == 100.0
    assert epic.business_value == 2000
    assert epic.description == "Security improvements across platform"

    # Relationships
    assert epic.entity_state.id == 4
    assert epic.entity_state.name == "Active"
    assert epic.project.name == "Project X"
    assert epic.team.name == "Security Team"


def test_epic_minimal_parsing() -> None:
    """Test Epic with minimal required fields."""
    data = {
        "Id": 777,
        "Name": "Minimal Epic",
        "ResourceType": "Epic",
        "CreateDate": None,
        "ModifyDate": None,
    }

    epic = Epic.model_validate(data)
    assert epic.id == 777
    assert epic.effort is None
    assert epic.business_value is None
    assert epic.entity_state is None
