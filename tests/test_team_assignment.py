"""Tests for TeamAssignment model."""

from datetime import datetime

from targetprocess.models import TeamAssignment


def test_team_assignment_full_parsing() -> None:
    data = {
        "Id": 2,
        "ResourceType": "TeamAssignment",
        "StartDate": "/Date(1424658067000+0100)/",
        "EndDate": "/Date(1427078912000+0100)/",
        "Team": {"Id": 214, "Name": "Ops"},
        "Assignable": {"Id": 247, "Name": "Story A"},
        "EntityState": {"Id": 82, "Name": "Open"},
    }
    ta = TeamAssignment.model_validate(data)
    assert ta.id == 2
    assert isinstance(ta.start_date, datetime) and ta.start_date.timestamp() == 1424658067.0
    assert isinstance(ta.end_date, datetime) and ta.end_date.timestamp() == 1427078912.0
    assert ta.team is not None and ta.team.name == "Ops"
    assert ta.assignable is not None and ta.assignable.id == 247
    assert ta.entity_state is not None and ta.entity_state.id == 82


def test_team_assignment_minimal_parsing() -> None:
    ta = TeamAssignment.model_validate({"Id": 9, "ResourceType": "TeamAssignment"})
    assert ta.id == 9
    assert ta.team is None and ta.assignable is None


def test_team_assignment_has_no_name_field() -> None:
    # TeamAssignment carries no Name on the wire -> extends Entity, not NamedEntity.
    ta = TeamAssignment.model_validate({"Id": 9})
    assert not hasattr(ta, "name")
