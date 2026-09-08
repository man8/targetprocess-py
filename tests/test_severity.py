"""Tests for Severity model."""

from targetprocess.models import Severity


def test_severity_full_parsing() -> None:
    severity = Severity.model_validate(
        {
            "Id": 1,
            "ResourceType": "Severity",
            "Name": "Blocking",
            "Importance": 1,
            "IsDefault": False,
            "IsMostImportant": True,
            "IsLeastImportant": False,
        }
    )
    assert severity.id == 1
    assert severity.name == "Blocking"
    assert severity.Name == "Blocking"
    assert severity.importance == 1
    assert severity.is_default is False
    assert severity.is_most_important is True
    assert severity.is_least_important is False
    assert severity.model_extra == {}


def test_severity_minimal_parsing() -> None:
    severity = Severity.model_validate({"Id": 5, "Name": "Small"})
    assert severity.id == 5
    assert severity.importance is None
    assert severity.is_default is None


def test_severity_preserves_undeclared_fields() -> None:
    severity = Severity.model_validate({"Id": 2, "Name": "Critical", "SomeFutureFlag": True})
    assert severity.model_extra is not None
    assert severity.model_extra["SomeFutureFlag"] is True
