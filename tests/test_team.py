"""Tests for Team model."""

from targetprocess.models import Team


def test_team_full_parsing() -> None:
    """Test Team parses complete API JSON."""
    data = {
        "Id": 123,
        "Name": "Dev Team",
        "ResourceType": "Team",
        "Description": "Main development team",
        "CreateDate": None,
        "ModifyDate": None,
    }

    team = Team.model_validate(data)

    # Base fields
    assert team.id == 123
    assert team.name == "Dev Team"
    assert team.resource_type == "Team"

    # Team-specific
    assert team.description == "Main development team"


def test_team_minimal_parsing() -> None:
    """Test Team with minimal required fields."""
    data = {
        "Id": 456,
        "Name": "Minimal Team",
        "ResourceType": "Team",
        "CreateDate": None,
        "ModifyDate": None,
    }

    team = Team.model_validate(data)
    assert team.id == 456
    assert team.description is None
