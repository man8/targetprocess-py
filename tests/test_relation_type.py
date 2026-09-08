"""Tests for RelationType model."""

from targetprocess.models import RelationType


def test_relation_type_parsing() -> None:
    rt = RelationType.model_validate({"Id": 2, "ResourceType": "RelationType", "Name": "Blocker"})
    assert rt.id == 2
    assert rt.name == "Blocker"
    assert rt.Name == "Blocker"


def test_relation_type_preserves_undeclared_fields() -> None:
    # Instance-specific extras stay reachable rather than being discarded.
    rt = RelationType.model_validate({"Id": 5, "Name": "Duplicate", "IsSystem": True})
    assert rt.model_extra is not None
    assert rt.model_extra["IsSystem"] is True
