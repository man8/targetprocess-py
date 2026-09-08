"""Tests for EntityType model (the full record, as against EntityTypeRef)."""

from targetprocess.models import EntityType


def test_entity_type_full_parsing() -> None:
    entity_type = EntityType.model_validate(
        {
            "Id": 4,
            "ResourceType": "EntityType",
            "Name": "UserStory",
            "CustomFieldScope": "Process",
            "IsSearchable": True,
            "IsUnitInHourOnly": False,
            "IsAssignable": True,
            "IsGlobal": False,
            "IsTeamAssignable": True,
            "HierarchyLevel": 3,
            "HasAuditHistory": True,
            "IsExtendable": True,
        }
    )
    assert entity_type.id == 4
    assert entity_type.name == "UserStory"
    assert entity_type.custom_field_scope == "Process"
    assert entity_type.is_searchable is True
    assert entity_type.is_unit_in_hour_only is False
    assert entity_type.is_assignable is True
    assert entity_type.is_global is False
    assert entity_type.is_team_assignable is True
    assert entity_type.hierarchy_level == 3
    assert entity_type.has_audit_history is True
    assert entity_type.is_extendable is True
    assert entity_type.model_extra == {}


def test_entity_type_minimal_parsing() -> None:
    entity_type = EntityType.model_validate({"Id": 8, "Name": "Bug"})
    assert entity_type.is_assignable is None
    assert entity_type.hierarchy_level is None


def test_entity_type_preserves_undeclared_fields() -> None:
    entity_type = EntityType.model_validate({"Id": 8, "Name": "Bug", "SomeFutureFlag": 1})
    assert entity_type.model_extra is not None
    assert entity_type.model_extra["SomeFutureFlag"] == 1
