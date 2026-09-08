"""Tests for CustomField model (field definition)."""

from targetprocess.models import CustomField


def test_custom_field_full_parsing() -> None:
    data = {
        "Id": 9,
        "Name": "ExampleField",
        "ResourceType": "CustomField",
        "Value": "ExampleValue",
        "FieldType": "DropDown",
        "EnabledForFilter": True,
        "Required": False,
        "NumericPriority": 3.0,
        "IsSystem": False,
        "Description": None,
        "Placeholder": None,
        "MaxTextLength": 4000,
        "EntityType": {"Id": 4, "Name": "UserStory"},
        "Process": {"Id": 2, "Name": "Scrum"},
    }
    cf = CustomField.model_validate(data)
    assert cf.id == 9
    assert cf.name == "ExampleField"
    assert cf.value == "ExampleValue"
    assert cf.field_type == "DropDown"
    assert cf.enabled_for_filter is True
    assert cf.required is False
    assert cf.numeric_priority == 3.0
    assert cf.is_system is False
    assert cf.max_text_length == 4000
    assert cf.entity_type is not None and cf.entity_type.id == 4
    assert cf.process is not None and cf.process.name == "Scrum"


def test_custom_field_minimal_parsing() -> None:
    cf = CustomField.model_validate({"Id": 1, "Name": "F", "ResourceType": "CustomField"})
    assert cf.id == 1
    assert cf.field_type is None
    assert cf.entity_type is None


def test_custom_field_non_string_value_carried() -> None:
    # value is typed `object`, so a non-string definition Value (should one ever
    # arrive) is carried faithfully rather than raising a whole-entity ParseError.
    cf = CustomField.model_validate(
        {"Id": 2, "Name": "N", "ResourceType": "CustomField", "Value": 5}
    )
    assert cf.value == 5
