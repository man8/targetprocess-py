"""Tests for Release model."""

from datetime import UTC, datetime, timedelta

from targetprocess.models import Release


def test_release_full_parsing() -> None:
    """Test Release parses complete API JSON, using real TP /Date()/ wire format."""
    data = {
        "Id": 123,
        "Name": "Release 1.0",
        "ResourceType": "Release",
        "StartDate": "/Date(1704067200000)/",  # 2024-01-01T00:00:00Z
        "EndDate": "/Date(1711929599000)/",  # 2024-03-31T23:59:59Z
        "Project": {"Id": 42, "Name": "Project X"},
        "Description": "First major release",
        "CreateDate": None,
        "ModifyDate": None,
    }

    release = Release.model_validate(data)

    # Base fields
    assert release.id == 123
    assert release.name == "Release 1.0"
    assert release.resource_type == "Release"

    # Release-specific
    assert release.start_date == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert release.end_date == datetime(2024, 3, 31, 23, 59, 59, tzinfo=UTC)
    assert release.start_date is not None and release.start_date.utcoffset() == timedelta(0)
    assert release.end_date is not None and release.end_date.utcoffset() == timedelta(0)
    assert release.description == "First major release"

    # Relationships
    assert release.project.id == 42
    assert release.project.name == "Project X"


def test_release_minimal_parsing() -> None:
    """Test Release with minimal required fields."""
    data = {
        "Id": 456,
        "Name": "Minimal Release",
        "ResourceType": "Release",
        "CreateDate": None,
        "ModifyDate": None,
    }

    release = Release.model_validate(data)
    assert release.id == 456
    assert release.start_date is None
    assert release.end_date is None
    assert release.project is None
    assert release.description is None
