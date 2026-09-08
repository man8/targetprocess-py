"""Tests for Iteration model."""

from datetime import datetime

from targetprocess.models import Iteration


def test_iteration_full_parsing() -> None:
    """Test Iteration parses complete API JSON."""
    data = {
        "Id": 123,
        "Name": "Sprint 1",
        "ResourceType": "Iteration",
        "StartDate": "2024-01-01T00:00:00",
        "EndDate": "2024-01-14T23:59:59",
        "Team": {"Id": 10, "Name": "Dev Team"},
        "Project": {"Id": 42, "Name": "Project X"},
        "Description": "First sprint of the year",
        "CreateDate": None,
        "ModifyDate": None,
    }

    iteration = Iteration.model_validate(data)

    # Base fields
    assert iteration.id == 123
    assert iteration.name == "Sprint 1"
    assert iteration.resource_type == "Iteration"

    # Iteration-specific
    assert iteration.start_date == datetime(2024, 1, 1, 0, 0, 0)
    assert iteration.end_date == datetime(2024, 1, 14, 23, 59, 59)
    assert iteration.description == "First sprint of the year"

    # Relationships
    assert iteration.team.id == 10
    assert iteration.team.name == "Dev Team"
    assert iteration.project.id == 42
    assert iteration.project.name == "Project X"


def test_iteration_minimal_parsing() -> None:
    """Test Iteration with minimal required fields."""
    data = {
        "Id": 456,
        "Name": "Minimal Iteration",
        "ResourceType": "Iteration",
        "CreateDate": None,
        "ModifyDate": None,
    }

    iteration = Iteration.model_validate(data)
    assert iteration.id == 456
    assert iteration.start_date is None
    assert iteration.end_date is None
    assert iteration.team is None
    assert iteration.project is None
    assert iteration.description is None
