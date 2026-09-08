"""Tests for Assignment model."""

from targetprocess.models import Assignment


def test_assignment_full_parsing() -> None:
    data = {
        "Id": 5501,
        "ResourceType": "Assignment",
        "GeneralUser": {
            "ResourceType": "GeneralUser",
            "Id": 6,
            "FirstName": "Alex",
            "LastName": "Dev",
            "Login": "alex",
            "FullName": "Alex Dev",
        },
        "Role": {"Id": 1, "Name": "Developer"},
        "Assignable": {"Id": 123, "Name": "Story A"},
    }
    a = Assignment.model_validate(data)
    assert a.id == 5501
    assert a.general_user is not None and a.general_user.id == 6
    assert a.general_user.full_name == "Alex Dev"
    assert a.role is not None and a.role.name == "Developer"
    assert a.assignable is not None and a.assignable.id == 123


def test_assignment_minimal_parsing() -> None:
    a = Assignment.model_validate({"Id": 9, "ResourceType": "Assignment"})
    assert a.id == 9
    assert a.general_user is None and a.role is None and a.assignable is None


def test_assignment_has_no_name_field() -> None:
    # Assignment carries no Name on the wire -> extends Entity, not NamedEntity.
    a = Assignment.model_validate({"Id": 9})
    assert not hasattr(a, "name")
