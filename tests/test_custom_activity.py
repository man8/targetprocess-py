"""Tests for CustomActivity model."""

from targetprocess.models import CustomActivity


def test_custom_activity_full_parsing() -> None:
    activity = CustomActivity.model_validate(
        {
            "Id": 21,
            "ResourceType": "CustomActivity",
            "Name": "Meetings",
            "Created": "/Date(1704067200000+0200)/",
            "Estimate": 4.5,
            "Project": {"ResourceType": "Project", "Id": 42, "Name": "Sample Project"},
            "User": {
                "ResourceType": "User",
                "Id": 7,
                "FirstName": "Alex",
                "LastName": "Example",
                "Login": "alex@example.com",
                "FullName": "Alex Example",
            },
        }
    )
    assert activity.id == 21
    assert activity.name == "Meetings"
    assert activity.created is not None and activity.created.year == 2024
    assert activity.estimate == 4.5
    assert activity.project is not None and activity.project.id == 42
    # User-shaped references carry no Name, so this must be a UserRef.
    assert activity.user is not None and activity.user.full_name == "Alex Example"
    assert activity.model_extra == {}


def test_custom_activity_minimal_parsing() -> None:
    activity = CustomActivity.model_validate({"Id": 22, "Name": "Support"})
    assert activity.created is None
    assert activity.user is None


def test_custom_activity_preserves_undeclared_fields() -> None:
    activity = CustomActivity.model_validate({"Id": 22, "Name": "Support", "Colour": "#336699"})
    assert activity.model_extra is not None
    assert activity.model_extra["Colour"] == "#336699"
