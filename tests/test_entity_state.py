"""Tests for EntityState model."""

from targetprocess.models import EntityState


def test_entity_state_full_parsing() -> None:
    """Test EntityState parses complete API JSON."""
    data = {
        "Id": 123,
        "Name": "In Progress",
        "ResourceType": "EntityState",
        "IsInitial": False,
        "IsFinal": False,
        "IsPlanned": True,
        "CreateDate": None,
        "ModifyDate": None,
    }

    state = EntityState.model_validate(data)

    # Base fields
    assert state.id == 123
    assert state.name == "In Progress"
    assert state.resource_type == "EntityState"

    # EntityState-specific
    assert state.is_initial is False
    assert state.is_final is False
    assert state.is_planned is True


def test_entity_state_minimal_parsing() -> None:
    """Test EntityState with minimal required fields."""
    data = {
        "Id": 456,
        "Name": "Minimal State",
        "ResourceType": "EntityState",
        "CreateDate": None,
        "ModifyDate": None,
    }

    state = EntityState.model_validate(data)
    assert state.id == 456
    assert state.is_initial is None
    assert state.is_final is None
    assert state.is_planned is None
