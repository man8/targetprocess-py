"""Tests for CustomRule model."""

from targetprocess.models import CustomRule


def test_custom_rule_full_parsing() -> None:
    rule = CustomRule.model_validate(
        {
            "Id": 9,
            "ResourceType": "CustomRule",
            "Name": "Close children with parent",
            "Description": "Sample rule description",
            "IsEnabled": True,
        }
    )
    assert rule.id == 9
    assert rule.name == "Close children with parent"
    assert rule.description == "Sample rule description"
    assert rule.is_enabled is True
    assert rule.model_extra == {}


def test_custom_rule_minimal_parsing() -> None:
    rule = CustomRule.model_validate({"Id": 10, "Name": "Sample rule"})
    assert rule.description is None
    assert rule.is_enabled is None


def test_custom_rule_preserves_undeclared_fields() -> None:
    rule = CustomRule.model_validate({"Id": 10, "Name": "Sample rule", "Trigger": "OnUpdate"})
    assert rule.model_extra is not None
    assert rule.model_extra["Trigger"] == "OnUpdate"
