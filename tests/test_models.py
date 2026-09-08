"""Tests for Entity models."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from targetprocess.models import Entity, NamedEntity, format_tp_date, parse_tp_date


def test_entity_initialization() -> None:
    """Test Entity can be initialized with just the required Id field."""
    entity = Entity(
        Id=123,
        ResourceType="User",
    )
    assert entity.Id == 123
    assert entity.ResourceType == "User"


def test_entity_has_no_name() -> None:
    """Test Entity (the common base, shared with User) has no Name field."""
    entity = Entity(Id=123, ResourceType="User")
    assert not hasattr(entity, "name")
    assert not hasattr(entity, "Name")


def test_entity_validation() -> None:
    """Test Entity validates only the required Id field (partial fetches)."""
    with pytest.raises(ValidationError) as exc_info:
        Entity()  # Missing required Id

    errors = exc_info.value.errors()
    required_fields = {error["loc"][0] for error in errors}
    assert required_fields == {"Id"}


def test_named_entity_pascalcase_access() -> None:
    """Test NamedEntity fields accessible via PascalCase (API format)."""
    entity = NamedEntity(
        Id=456,
        Name="Another Entity",
        ResourceType="Bug",
        CreateDate=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    assert entity.Id == 456
    assert entity.Name == "Another Entity"
    assert entity.ResourceType == "Bug"
    assert entity.CreateDate == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_named_entity_snake_case_access() -> None:
    """Test NamedEntity fields accessible via snake_case (Python style)."""
    entity = NamedEntity(
        Id=789,
        Name="Snake Case Entity",
        ResourceType="Task",
        CreateDate=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    assert entity.id == 789
    assert entity.name == "Snake Case Entity"
    assert entity.resource_type == "Task"
    assert entity.create_date == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_named_entity_validation() -> None:
    """Test NamedEntity still only requires Id; Name stays optional."""
    with pytest.raises(ValidationError) as exc_info:
        NamedEntity()  # Missing required Id

    errors = exc_info.value.errors()
    required_fields = {error["loc"][0] for error in errors}
    assert required_fields == {"Id"}


def test_parse_tp_date_wire_format() -> None:
    """Test parse_tp_date converts TP wire format with positive offset."""
    dt = parse_tp_date("/Date(1493188560000+0300)/")
    assert isinstance(dt, datetime)
    assert dt == datetime.fromtimestamp(1493188560000 / 1000, tz=timezone(timedelta(hours=3)))
    # Aware-datetime equality above only proves the same instant - it would
    # also pass for a UTC result. Assert the +0300 offset explicitly.
    assert dt.utcoffset() == timedelta(hours=3)


def test_parse_tp_date_negative_offset() -> None:
    """Test parse_tp_date converts TP wire format with negative offset."""
    dt = parse_tp_date("/Date(1493188560000-0500)/")
    assert isinstance(dt, datetime)
    assert dt.utcoffset() == timedelta(hours=-5)


def test_parse_tp_date_no_offset() -> None:
    """Test parse_tp_date assumes UTC when no offset is present."""
    dt = parse_tp_date("/Date(1493188560000)/")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None  # UTC assumed


def test_parse_tp_date_passthrough() -> None:
    """Test parse_tp_date passes through non-wire-format values untouched."""
    now = datetime.now(tz=UTC)
    assert parse_tp_date(now) is now
    assert parse_tp_date(None) is None
    assert (
        parse_tp_date("2026-07-21T10:00:00Z") == "2026-07-21T10:00:00Z"
    )  # ISO handled by pydantic


def test_entity_parses_wire_dates() -> None:
    """Test Entity.model_validate parses TP wire-format CreateDate."""
    e = Entity.model_validate(
        {"Id": 1, "ResourceType": "User", "CreateDate": "/Date(1493188560000+0300)/"}
    )
    assert e.create_date is not None and e.create_date.year == 2017


def test_format_tp_date_utc() -> None:
    dt = datetime(2024, 6, 14, 12, 0, tzinfo=UTC)
    assert format_tp_date(dt) == "/Date(1718366400000+0000)/"


def test_format_tp_date_positive_offset() -> None:
    tz = timezone(timedelta(hours=2))
    dt = datetime(2024, 6, 14, 14, 0, tzinfo=tz)
    assert format_tp_date(dt) == "/Date(1718366400000+0200)/"


def test_format_tp_date_negative_offset() -> None:
    tz = timezone(timedelta(hours=-5))
    dt = datetime(2024, 6, 14, 7, 0, tzinfo=tz)
    assert format_tp_date(dt) == "/Date(1718366400000-0500)/"


def test_format_tp_date_half_hour_offset() -> None:
    tz = timezone(timedelta(hours=5, minutes=30))
    dt = datetime(2024, 6, 14, 17, 30, tzinfo=tz)
    assert format_tp_date(dt) == "/Date(1718366400000+0530)/"


def test_format_tp_date_rejects_naive() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        format_tp_date(datetime(2024, 6, 14, 12, 0))


def test_format_tp_date_rejects_sub_minute_offset() -> None:
    tz = timezone(timedelta(hours=1, seconds=30))
    assert tz.utcoffset(None) == timedelta(hours=1, seconds=30)
    dt = datetime(2024, 6, 14, 12, 0, tzinfo=tz)
    with pytest.raises(ValueError, match="whole-minute"):
        format_tp_date(dt)


def test_format_tp_date_round_trips_through_parse_tp_date() -> None:
    tz = timezone(timedelta(hours=2))
    dt = datetime(2024, 6, 14, 14, 0, tzinfo=tz)
    parsed = parse_tp_date(format_tp_date(dt))
    assert isinstance(parsed, datetime)
    assert parsed == dt
    assert parsed.utcoffset() == dt.utcoffset()


def test_format_tp_date_pre_epoch() -> None:
    # Half a millisecond before the epoch. Scaling timestamp() gives -0.5,
    # which int() truncates toward zero to 0; floor division gives -1. This
    # test fails on the truncating implementation and passes on the floor one.
    dt = datetime(1969, 12, 31, 23, 59, 59, 999500, tzinfo=UTC)
    assert format_tp_date(dt) == "/Date(-1+0000)/"
