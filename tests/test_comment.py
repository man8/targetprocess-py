"""Tests for Comment model."""

from datetime import datetime

from targetprocess.models import Comment


def test_comment_full_parsing() -> None:
    data = {
        "Id": 111213,
        "ResourceType": "Comment",
        "Description": "a comment body",
        "ParentId": 111167,
        "CreateDate": "/Date(1784639085000+0200)/",
        "DescriptionModifyDate": "/Date(1784639085000+0200)/",
        "IsPrivate": False,
        "IsPinned": False,
        "General": {"Id": 74270, "Name": "Story A"},
        "Owner": {"ResourceType": "GeneralUser", "Id": 22, "FullName": "Jane Doe"},
        "EntityVersion": 46004869,
    }
    c = Comment.model_validate(data)
    assert c.id == 111213
    assert c.description == "a comment body"
    assert c.parent_id == 111167
    assert isinstance(c.create_date, datetime) and c.create_date.timestamp() == 1784639085.0
    assert isinstance(c.description_modify_date, datetime)
    assert c.description_modify_date.timestamp() == 1784639085.0
    assert c.is_private is False
    assert c.is_pinned is False
    assert c.general is not None and c.general.id == 74270
    assert c.owner is not None and c.owner.id == 22 and c.owner.full_name == "Jane Doe"
    assert c.entity_version == 46004869


def test_comment_entity_version_is_declared() -> None:
    # EntityVersion is a declared field, not an extra="allow" passthrough.
    c = Comment.model_validate({"Id": 7, "ResourceType": "Comment", "EntityVersion": 42})
    assert c.entity_version == 42
    assert "EntityVersion" not in (c.model_extra or {})


def test_comment_minimal_parsing() -> None:
    c = Comment.model_validate({"Id": 5, "ResourceType": "Comment"})
    assert c.id == 5
    assert c.parent_id is None
    assert c.owner is None
    assert c.description_modify_date is None


def test_comment_top_level_has_null_parent() -> None:
    c = Comment.model_validate({"Id": 6, "ResourceType": "Comment", "ParentId": None})
    assert c.parent_id is None


def test_comment_has_no_name_field() -> None:
    # Comment carries no Name on the wire -> extends Entity, not NamedEntity.
    c = Comment.model_validate({"Id": 6})
    assert not hasattr(c, "name")
