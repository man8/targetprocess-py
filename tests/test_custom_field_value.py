"""Tests for CustomFieldValue model (embedded value element)."""

from targetprocess.models import CustomFieldValue


def test_custom_field_value_string() -> None:
    cfv = CustomFieldValue.model_validate(
        {"Name": "ExampleDropdown", "Type": "DropDown", "Value": "High"}
    )
    assert cfv.name == "ExampleDropdown"
    assert cfv.type == "DropDown"
    assert cfv.value == "High"


def test_custom_field_value_number() -> None:
    cfv = CustomFieldValue.model_validate(
        {"Name": "ExampleNumber", "Type": "Number", "Value": 1500.0}
    )
    assert cfv.value == 1500.0
    assert isinstance(cfv.value, float)


def test_custom_field_value_checkbox() -> None:
    cfv = CustomFieldValue.model_validate(
        {"Name": "ExampleCheckbox", "Type": "CheckBox", "Value": True}
    )
    assert cfv.value is True


def test_custom_field_value_null() -> None:
    cfv = CustomFieldValue.model_validate(
        {"Name": "ExampleCategory", "Type": "DropDown", "Value": None}
    )
    assert cfv.value is None


def test_custom_field_value_date_carried_as_wire_string() -> None:
    # Date-typed custom values arrive as TP /Date(ms±HHMM)/ wire strings.
    # `value` is `object` (no TPDateTime coercion), so the raw wire string is
    # carried faithfully and unchanged - deliberate; consumers can pass it
    # through parse_tp_date if they want a datetime.
    raw = "/Date(1784639085000+0200)/"
    cfv = CustomFieldValue.model_validate({"Name": "ExampleDate", "Type": "Date", "Value": raw})
    assert cfv.value == raw
    assert isinstance(cfv.value, str)


def test_custom_field_value_populate_by_name() -> None:
    cfv = CustomFieldValue(name="X", type="Text", value="y")
    assert cfv.name == "X" and cfv.type == "Text" and cfv.value == "y"
