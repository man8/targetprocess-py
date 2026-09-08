"""Tests for Role model."""

from targetprocess.models import Role


def test_role_parsing() -> None:
    role = Role.model_validate({"Id": 1, "ResourceType": "Role", "Name": "Developer"})
    assert role.id == 1
    assert role.name == "Developer"
    assert role.Name == "Developer"


def test_role_declares_its_permission_flags() -> None:
    role = Role.model_validate(
        {
            "Id": 2,
            "Name": "QA Engineer",
            "Description": "Tests things",
            "HasEffort": True,
            "CanChangeOwner": False,
            "CanPrioritize": False,
            "CanUsePersonalAccessTokens": True,
            "TimeSheetAccess": True,
        }
    )
    assert role.description == "Tests things"
    assert role.has_effort is True
    assert role.can_change_owner is False
    assert role.can_prioritize is False
    assert role.can_use_personal_access_tokens is True
    assert role.time_sheet_access is True
    assert role.model_extra == {}


def test_role_preserves_undeclared_fields() -> None:
    # Instance-specific extras stay reachable rather than being discarded.
    role = Role.model_validate({"Id": 2, "Name": "QA Engineer", "SomeFutureFlag": True})
    assert role.model_extra is not None
    assert role.model_extra["SomeFutureFlag"] is True
