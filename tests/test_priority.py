"""Tests for the Priority model."""

from targetprocess.exceptions import AmbiguousMatchError, TargetProcessError
from targetprocess.models import Priority


def test_priority_parses_wire_shape():
    data = {
        "ResourceType": "Priority",
        "Id": 1,
        "Name": "Must Have",
        "Importance": 1,
        "IsDefault": False,
        "EntityType": {"ResourceType": "EntityType", "Id": 4, "Name": "UserStory"},
    }

    priority = Priority.model_validate(data)

    assert priority.id == 1
    assert priority.name == "Must Have"
    assert priority.importance == 1
    assert priority.is_default is False
    assert priority.entity_type is not None
    assert priority.entity_type.id == 4
    assert priority.entity_type.name == "UserStory"


def test_priority_tolerates_absent_entity_type():
    priority = Priority.model_validate({"Id": 5, "Name": "Nice To Have"})

    assert priority.entity_type is None
    assert priority.importance is None
    assert priority.is_default is None


def test_ambiguous_match_error_is_a_targetprocess_error():
    assert issubclass(AmbiguousMatchError, TargetProcessError)
