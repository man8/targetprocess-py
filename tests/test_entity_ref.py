"""Tests for EntityRef model."""

from targetprocess.models import EntityRef


def test_entity_ref_parsing() -> None:
    """Test EntityRef parses from API JSON."""
    data = {"Id": 123, "Name": "Test Project"}
    ref = EntityRef.model_validate(data)
    assert ref.id == 123
    assert ref.name == "Test Project"


def test_entity_ref_optional_fields() -> None:
    """Test EntityRef handles minimal data - Name is genuinely optional."""
    data = {"Id": 456, "ResourceType": "Project"}
    ref = EntityRef.model_validate(data)
    assert ref.id == 456
    assert ref.name is None


def test_all_models_exported() -> None:
    """Test all models are exported from package."""
    from targetprocess import (
        Attachment,
        Bug,
        Comment,
        CustomField,
        CustomFieldValue,
        Entity,
        EntityRef,
        EntityState,
        Epic,
        Feature,
        Iteration,
        Project,
        Release,
        Request,
        RoleEffort,
        Task,
        Team,
        TeamAssignment,
        TeamIteration,
        TestCase,
        User,
        UserRef,
        UserStory,
    )

    # Verify all classes accessible
    assert Entity is not None
    assert EntityRef is not None
    assert UserRef is not None
    assert UserStory is not None
    assert Bug is not None
    assert Task is not None
    assert Feature is not None
    assert Epic is not None
    assert Request is not None
    assert TestCase is not None
    assert Release is not None
    assert Iteration is not None
    assert Project is not None
    assert Team is not None
    assert User is not None
    assert EntityState is not None
    # Join entities
    assert TeamIteration is not None
    assert TeamAssignment is not None
    assert RoleEffort is not None
    # Supporting entities
    assert Comment is not None
    assert Attachment is not None
    # Custom-field entities
    assert CustomField is not None
    assert CustomFieldValue is not None

    import targetprocess

    assert {
        "TeamIteration",
        "TeamAssignment",
        "RoleEffort",
        "Comment",
        "Attachment",
        "CustomField",
        "CustomFieldValue",
    }.issubset(targetprocess.__all__)
