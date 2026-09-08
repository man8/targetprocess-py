"""Tests for Feature model."""

from targetprocess.models import Feature


def test_feature_full_parsing() -> None:
    """Test Feature parses complete API JSON."""
    data = {
        "Id": 555,
        "Name": "OAuth Authentication",
        "ResourceType": "Feature",
        "Effort": 21.0,
        "BusinessValue": 500,
        "Description": "Implement OAuth 2.0 authentication",
        "EntityState": {"Id": 3, "Name": "In Development"},
        "Project": {"Id": 42, "Name": "Project X"},
        "Team": {"Id": 10, "Name": "Platform Team"},
        "Epic": {"Id": 999, "Name": "Security Features"},
        "CreateDate": None,
        "ModifyDate": None,
    }

    feature = Feature.model_validate(data)

    # Base fields
    assert feature.id == 555
    assert feature.name == "OAuth Authentication"
    assert feature.resource_type == "Feature"

    # Feature-specific
    assert feature.effort == 21.0
    assert feature.business_value == 500
    assert feature.description == "Implement OAuth 2.0 authentication"

    # Relationships
    assert feature.entity_state.id == 3
    assert feature.entity_state.name == "In Development"
    assert feature.project.name == "Project X"
    assert feature.team.name == "Platform Team"
    assert feature.epic.id == 999


def test_feature_minimal_parsing() -> None:
    """Test Feature with minimal required fields."""
    data = {
        "Id": 666,
        "Name": "Minimal Feature",
        "ResourceType": "Feature",
        "CreateDate": None,
        "ModifyDate": None,
    }

    feature = Feature.model_validate(data)
    assert feature.id == 666
    assert feature.effort is None
    assert feature.business_value is None
    assert feature.entity_state is None
    assert feature.epic is None


def test_feature_business_value_accepts_whatever_tp_sends() -> None:
    """A server-supplied number carries no range constraint.

    TP computes this and documents no bound. A constraint here would fail the
    whole entity rather than the field, so one odd value would abort an entire
    list() page. Range checks belong on the write side, where the value
    originates - see ``times.upsert``.
    """
    entity = Feature.model_validate(
        {"Id": 999, "Name": "Odd but parseable", "ResourceType": "Feature", "BusinessValue": -100}
    )
    assert entity.business_value == -100
    assert entity.name == "Odd but parseable"
