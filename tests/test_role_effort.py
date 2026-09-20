"""Tests for RoleEffort model."""

import pytest

from targetprocess_py.models import RoleEffort


def test_role_effort_full_parsing() -> None:
    data = {
        "Id": 456100,
        "ResourceType": "RoleEffort",
        "InitialEstimate": 0.0,
        "Effort": 2.0,
        "EffortCompleted": 0.0,
        "EffortToDo": 2.0,
        "TimeSpent": 0.0,
        "TimeRemain": 2.0,
        "Assignable": {"Id": 51383, "Name": "Story B"},
        "Role": {"Id": 20, "Name": "Developer"},
    }
    re = RoleEffort.model_validate(data)
    assert re.id == 456100
    assert re.initial_estimate == 0.0
    assert re.effort == 2.0
    assert re.effort_completed == 0.0
    assert re.effort_todo == 2.0
    assert re.time_spent == 0.0
    assert re.time_remain == 2.0
    assert re.assignable is not None and re.assignable.id == 51383
    assert re.role is not None and re.role.name == "Developer"


def test_role_effort_minimal_parsing() -> None:
    re = RoleEffort.model_validate({"Id": 1, "ResourceType": "RoleEffort"})
    assert re.id == 1
    assert re.effort is None and re.role is None


@pytest.mark.parametrize(
    ("alias", "attribute"),
    [
        ("InitialEstimate", "initial_estimate"),
        ("Effort", "effort"),
        ("EffortCompleted", "effort_completed"),
        ("EffortToDo", "effort_todo"),
        ("TimeSpent", "time_spent"),
        ("TimeRemain", "time_remain"),
    ],
)
def test_role_effort_parses_a_negative_roll_up_the_server_sent(alias: str, attribute: str) -> None:
    # Every one of these is a server-computed roll-up, so none constrains its
    # range: a constraint on a server-supplied value fails the whole entity
    # rather than the field, and one out-of-range roll-up would abort a whole
    # list() page with a ParseError. Reporting what TP sent is worth more than
    # asserting an invariant the API never promised.
    effort = RoleEffort.model_validate({"Id": 2, "ResourceType": "RoleEffort", alias: -1.0})
    assert getattr(effort, attribute) == -1.0


def test_role_effort_has_no_name_field() -> None:
    # RoleEffort carries no Name on the wire -> extends Entity, not NamedEntity.
    re = RoleEffort.model_validate({"Id": 1})
    assert not hasattr(re, "name")
