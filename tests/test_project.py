"""Tests for Project model."""

from datetime import datetime

from targetprocess.models import Project


def test_project_full_parsing() -> None:
    """Test Project parses complete API JSON."""
    data = {
        "Id": 123,
        "Name": "Project X",
        "ResourceType": "Project",
        "StartDate": "2024-01-01T00:00:00",
        "EndDate": "2024-12-31T23:59:59",
        "Company": {"Id": 1, "Name": "Acme Corp"},
        "Description": "Main project for 2024",
        "CreateDate": None,
        "ModifyDate": None,
    }

    project = Project.model_validate(data)

    # Base fields
    assert project.id == 123
    assert project.name == "Project X"
    assert project.resource_type == "Project"

    # Project-specific
    assert project.start_date == datetime(2024, 1, 1, 0, 0, 0)
    assert project.end_date == datetime(2024, 12, 31, 23, 59, 59)
    assert project.description == "Main project for 2024"

    # Relationships
    assert project.company.id == 1
    assert project.company.name == "Acme Corp"


def test_project_minimal_parsing() -> None:
    """Test Project with minimal required fields."""
    data = {
        "Id": 456,
        "Name": "Minimal Project",
        "ResourceType": "Project",
        "CreateDate": None,
        "ModifyDate": None,
    }

    project = Project.model_validate(data)
    assert project.id == 456
    assert project.start_date is None
    assert project.end_date is None
    assert project.company is None
    assert project.description is None


def test_project_partial_fetch_validates() -> None:
    # include=[Id] style partial payloads must not fail on missing fields
    project = Project.model_validate({"ResourceType": "Project", "Id": 42})
    assert project.id == 42 and project.name is None
