"""Tests for Relation model."""

from targetprocess.models import Relation


def test_relation_full_parsing() -> None:
    # The blocking item is always the Master; the Slave is the blocked one.
    data = {
        "Id": 53,
        "ResourceType": "Relation",
        "Master": {"ResourceType": "UserStory", "Id": 188, "Name": "Blocking story"},
        "Slave": {"ResourceType": "Bug", "Id": 187, "Name": "Blocked bug"},
        "RelationType": {"ResourceType": "RelationType", "Id": 2, "Name": "Blocker"},
    }
    r = Relation.model_validate(data)
    assert r.id == 53
    assert r.master is not None and r.master.id == 188
    assert r.slave is not None and r.slave.id == 187
    assert r.relation_type is not None and r.relation_type.name == "Blocker"


def test_relation_minimal_parsing() -> None:
    r = Relation.model_validate({"Id": 9, "ResourceType": "Relation"})
    assert r.id == 9
    assert r.master is None and r.slave is None and r.relation_type is None


def test_relation_has_no_name_field() -> None:
    # Relation carries no Name on the wire -> extends Entity, not NamedEntity.
    r = Relation.model_validate({"Id": 9})
    assert not hasattr(r, "name")


def test_relation_preserves_undeclared_fields() -> None:
    # The API declares more reference properties than the model; extras stay
    # reachable in model_extra rather than being discarded.
    r = Relation.model_validate({"Id": 9, "SomeOtherRef": {"Id": 1}})
    assert r.model_extra is not None
    assert r.model_extra["SomeOtherRef"] == {"Id": 1}
