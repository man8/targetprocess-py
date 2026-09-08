"""Tests for TeamIteration model."""

from datetime import datetime

from targetprocess.models import TeamIteration


def test_team_iteration_full_parsing() -> None:
    data = {
        "Id": 68611,
        "Name": "Sprint 42",
        "ResourceType": "TeamIteration",
        "StartDate": "/Date(1804460400000+0100)/",
        "EndDate": "/Date(1805497199000+0100)/",
        "Effort": 120.0,
        "EffortCompleted": 29.0,
        "EffortToDo": 91.0,
        "Velocity": 0.0,
        "Capacity": 0.0,
        "IsCurrent": False,
        "Team": {"Id": 51642, "Name": "Dev Team"},
        "Release": {"Id": 66703, "Name": "R1"},
        "Project": {"Id": 42, "Name": "Project X"},
        "Description": "sprint description",
    }
    ti = TeamIteration.model_validate(data)
    assert ti.id == 68611
    assert ti.name == "Sprint 42"
    assert ti.resource_type == "TeamIteration"
    assert isinstance(ti.start_date, datetime) and ti.start_date.timestamp() == 1804460400.0
    assert isinstance(ti.end_date, datetime) and ti.end_date.timestamp() == 1805497199.0
    assert ti.effort == 120.0
    assert ti.effort_completed == 29.0
    assert ti.effort_todo == 91.0
    assert ti.velocity == 0.0
    assert ti.capacity == 0.0
    assert ti.is_current is False
    assert ti.description == "sprint description"
    assert ti.team is not None and ti.team.id == 51642
    assert ti.release is not None and ti.release.name == "R1"
    assert ti.project is not None and ti.project.id == 42


def test_team_iteration_minimal_parsing() -> None:
    ti = TeamIteration.model_validate({"Id": 1, "Name": "Min", "ResourceType": "TeamIteration"})
    assert ti.id == 1
    assert ti.effort is None
    assert ti.team is None


def test_team_iteration_effort_accepts_whatever_tp_sends() -> None:
    """A server-supplied roll-up carries no range constraint.

    TP computes this and documents no bound. A constraint here would fail the
    whole entity rather than the field, so one odd roll-up would abort an
    entire list() page. Range checks belong on the write side, where the value
    originates - see ``times.upsert``.
    """
    ti = TeamIteration.model_validate(
        {"Id": 2, "Name": "Odd but parseable", "ResourceType": "TeamIteration", "Effort": -1.0}
    )
    assert ti.effort == -1.0
    assert ti.name == "Odd but parseable"


def test_team_iteration_tolerates_unmodelled_extra_keys() -> None:
    # A key the models do not declare is not a parse error and is preserved in
    # model_extra (extra="allow" on the Entity base), while the General-base
    # fields and CustomFields parse into their declared attributes.
    ti = TeamIteration.model_validate(
        {
            "Id": 7,
            "Name": "With extras",
            "ResourceType": "TeamIteration",
            "NumericPriority": 662.0,
            "Owner": {"ResourceType": "GeneralUser", "Id": 31, "FullName": "Someone"},
            "CustomFields": [{"Name": "X", "Type": "Text", "Value": "y"}],
            "SomeFutureField": "kept",
        }
    )
    assert ti.id == 7
    assert ti.name == "With extras"
    assert ti.custom_fields is not None
    assert ti.custom_fields[0].name == "X"
    # Declared on the model, so these parse rather than landing in extras.
    assert ti.numeric_priority == 662.0
    assert ti.owner is not None
    assert ti.owner.full_name == "Someone"
    # Still undeclared, so still preserved.
    assert ti.model_extra is not None
    assert ti.model_extra["SomeFutureField"] == "kept"
