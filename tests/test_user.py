"""Tests for User model."""

from targetprocess.models import User


def test_user_full_parsing() -> None:
    """Test User parses complete API JSON."""
    data = {
        "Id": 123,
        "ResourceType": "User",
        "Email": "john.doe@example.com",
        "FirstName": "John",
        "LastName": "Doe",
        "Login": "jdoe",
        "FullName": "John Doe",
        "IsActive": True,
        "Role": {"Id": 1, "Name": "Developer"},
        "CreateDate": None,
        "ModifyDate": None,
    }

    user = User.model_validate(data)

    # Base fields
    assert user.id == 123
    assert user.resource_type == "User"
    assert not hasattr(user, "name")

    # User-specific
    assert user.email == "john.doe@example.com"
    assert user.first_name == "John"
    assert user.last_name == "Doe"
    assert user.login == "jdoe"
    assert user.full_name == "John Doe"
    assert user.is_active is True

    # Relationships
    assert user.role is not None
    assert user.role.id == 1
    assert user.role.name == "Developer"


def test_user_minimal_parsing() -> None:
    """Test User with minimal required fields."""
    data = {
        "Id": 456,
        "ResourceType": "User",
        "CreateDate": None,
        "ModifyDate": None,
    }

    user = User.model_validate(data)
    assert user.id == 456
    assert user.email is None
    assert user.first_name is None
    assert user.last_name is None
    assert user.login is None
    assert user.full_name is None
    assert user.is_active is None
    assert user.role is None


def test_user_partial_fetch_validates() -> None:
    # include=[Id] style partial payloads must not fail on missing fields
    user = User.model_validate({"ResourceType": "User", "Id": 7})
    assert user.id == 7 and user.full_name is None


def test_user_real_payload_shape() -> None:
    u = User.model_validate(
        {
            "ResourceType": "User",
            "Id": 7,
            "FirstName": "Ada",
            "LastName": "L",
            "Email": "ada@example.com",
            "Login": "ada",
            "FullName": "Ada L",
            "CreateDate": "/Date(1493188560000+0300)/",
        }
    )
    assert u.id == 7 and u.full_name == "Ada L" and not hasattr(u, "name")
