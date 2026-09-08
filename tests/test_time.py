"""Tests for Time model."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from targetprocess.models import Time


def test_time_full_parsing() -> None:
    data = {
        "Id": 987654,
        "ResourceType": "Time",
        "Description": "Investigated the failing sync",
        "Spent": 2.5,
        "Remain": 0.0,
        "IsEstimation": False,
        "Date": "/Date(1718366400000+0200)/",
        "Assignable": {"Id": 51383, "Name": "Story B"},
        "User": {
            "ResourceType": "User",
            "Id": 1,
            "FirstName": "Ada",
            "LastName": "Lovelace",
            "Login": "ada",
            "FullName": "Ada Lovelace",
        },
        "Project": {"Id": 300, "Name": "Platform"},
        "Role": {"Id": 20, "Name": "Developer"},
    }
    time = Time.model_validate(data)
    assert time.id == 987654
    assert time.spent == 2.5
    assert time.remain == 0.0
    assert time.is_estimation is False
    assert time.description == "Investigated the failing sync"
    assert isinstance(time.date, datetime)
    assert time.date.utcoffset() is not None
    assert time.assignable is not None and time.assignable.id == 51383
    assert time.user is not None and time.user.full_name == "Ada Lovelace"
    assert time.project is not None and time.project.id == 300
    assert time.role is not None and time.role.name == "Developer"


def test_time_minimal_parsing() -> None:
    time = Time.model_validate({"Id": 1, "ResourceType": "Time"})
    assert time.id == 1
    assert time.spent is None
    assert time.date is None
    assert time.assignable is None


def test_time_user_uses_user_ref_shape() -> None:
    # TP sends the User reference with no Name key, so EntityRef would not fit.
    time = Time.model_validate({"Id": 1, "User": {"ResourceType": "User", "Id": 7, "Login": "ada"}})
    assert time.user is not None
    assert time.user.login == "ada"
    assert not hasattr(time.user, "name")


def test_time_has_no_name_field() -> None:
    # TP's Time carries no Name on the wire -> extends Entity, not NamedEntity.
    time = Time.model_validate({"Id": 1})
    assert not hasattr(time, "name")


def test_time_pascal_case_accessors() -> None:
    time = Time.model_validate({"Id": 5, "ResourceType": "Time"})
    assert time.Id == 5
    assert time.ResourceType == "Time"


@pytest.mark.parametrize("field", ["Spent", "Remain"])
def test_time_rejects_negative_hours(field: str) -> None:
    with pytest.raises(ValidationError):
        Time.model_validate({"Id": 2, "ResourceType": "Time", field: -1.0})


def test_time_declares_the_narrow_back_references() -> None:
    # TP populates exactly one narrow back-reference per entry alongside (or
    # instead of) Assignable; each parses into its own attribute.
    time = Time.model_validate(
        {"Id": 3, "UserStory": {"Id": 9, "Name": "Story"}, "CustomFields": []}
    )
    assert time.id == 3
    assert time.user_story is not None
    assert time.user_story.id == 9
    assert time.user_story.name == "Story"
    assert time.task is None
    assert time.bug is None
    assert time.assignable is None
    assert time.model_extra == {}


def test_time_back_reference_covers_a_custom_activity_entry() -> None:
    # A CustomActivity entry has no Assignable at all - the back-reference is
    # the only record of what the time was logged against.
    time = Time.model_validate(
        {"Id": 4, "CustomActivity": {"Id": 47, "Name": "Admin"}, "Assignable": None}
    )
    assert time.assignable is None
    assert time.custom_activity is not None
    assert time.custom_activity.name == "Admin"


def test_time_tolerates_unmodelled_keys() -> None:
    # Extras are preserved in model_extra rather than dropped.
    time = Time.model_validate({"Id": 3, "SomeFutureField": "kept", "CustomFields": []})
    assert time.model_extra is not None
    assert time.model_extra["SomeFutureField"] == "kept"
