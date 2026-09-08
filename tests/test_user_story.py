"""Tests for UserStory model."""

from targetprocess.models import UserStory


def test_user_story_full_parsing() -> None:
    """Test UserStory parses complete API JSON."""
    data = {
        "Id": 123,
        "Name": "User Login",
        "ResourceType": "UserStory",
        "Effort": 5.0,
        "Description": "As a user, I want to login",
        "EntityState": {"Id": 1, "Name": "Open"},
        "Project": {"Id": 42, "Name": "Project X"},
        "AssignedUser": {"Items": [{"ResourceType": "User", "Id": 99, "FullName": "John Doe"}]},
        "Team": {"Id": 10, "Name": "Dev Team"},
        "CreateDate": None,
        "ModifyDate": None,
    }

    story = UserStory.model_validate(data)

    # Base fields
    assert story.id == 123
    assert story.name == "User Login"
    assert story.resource_type == "UserStory"

    # UserStory-specific
    assert story.effort == 5.0
    assert story.description == "As a user, I want to login"

    # Relationships
    assert story.entity_state is not None and story.entity_state.id == 1
    assert story.project is not None and story.project.name == "Project X"
    assert story.assigned_user is not None
    assert story.assigned_user[0].id == 99
    assert story.team is not None and story.team.name == "Dev Team"


def test_user_story_minimal_parsing() -> None:
    """Test UserStory with minimal required fields."""
    data = {
        "Id": 456,
        "Name": "Minimal Story",
        "ResourceType": "UserStory",
        "CreateDate": None,
        "ModifyDate": None,
    }

    story = UserStory.model_validate(data)
    assert story.id == 456
    assert story.effort is None
    assert story.entity_state is None


def test_user_story_effort_accepts_whatever_tp_sends() -> None:
    """A server-supplied number carries no range constraint.

    TP computes this and documents no bound. A constraint here would fail the
    whole entity rather than the field, so one odd value would abort an entire
    list() page. Range checks belong on the write side, where the value
    originates - see ``times.upsert``.
    """
    entity = UserStory.model_validate(
        {"Id": 999, "Name": "Odd but parseable", "ResourceType": "UserStory", "Effort": -1.0}
    )
    assert entity.effort == -1.0
    assert entity.name == "Odd but parseable"


def test_user_story_partial_fetch_validates() -> None:
    # include=[Id] style partial payloads must not fail on missing fields
    story = UserStory.model_validate({"ResourceType": "UserStory", "Id": 42})
    assert story.id == 42 and story.name is None
