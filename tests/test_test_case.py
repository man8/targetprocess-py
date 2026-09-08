"""Tests for TestCase model."""

from targetprocess.models import TestCase


def test_test_case_full_parsing() -> None:
    """Test TestCase parses complete API JSON."""
    data = {
        "Id": 444,
        "Name": "Login flow test",
        "ResourceType": "TestCase",
        "Description": "Test user login with valid credentials",
        "EntityState": {"Id": 6, "Name": "Ready"},
        "Project": {"Id": 42, "Name": "Project X"},
        "AssignedUser": {"Items": [{"ResourceType": "User", "Id": 99, "FullName": "Jane Tester"}]},
        "CreateDate": None,
        "ModifyDate": None,
    }

    test_case = TestCase.model_validate(data)

    # Base fields
    assert test_case.id == 444
    assert test_case.name == "Login flow test"
    assert test_case.resource_type == "TestCase"

    # TestCase-specific
    assert test_case.description == "Test user login with valid credentials"

    # Relationships
    assert test_case.entity_state is not None and test_case.entity_state.id == 6
    assert test_case.entity_state.name == "Ready"
    assert test_case.project is not None and test_case.project.name == "Project X"
    assert test_case.assigned_user is not None
    assert test_case.assigned_user[0].id == 99


def test_test_case_minimal_parsing() -> None:
    """Test TestCase with minimal required fields."""
    data = {
        "Id": 555,
        "Name": "Minimal TestCase",
        "ResourceType": "TestCase",
        "CreateDate": None,
        "ModifyDate": None,
    }

    test_case = TestCase.model_validate(data)
    assert test_case.id == 555
    assert test_case.description is None
    assert test_case.entity_state is None
    assert test_case.assigned_user is None
