"""Tests for targetprocess type definitions."""

from dataclasses import FrozenInstanceError

import pytest

from targetprocess.models import Time
from targetprocess.types import ClientMode, UpsertAction, UpsertResult


def test_client_mode_values() -> None:
    """Test ClientMode enum has correct values."""
    assert ClientMode.READONLY.value == "readonly"
    assert ClientMode.READWRITE.value == "readwrite"


def test_client_mode_string_conversion() -> None:
    """Test ClientMode can be created from strings."""
    assert ClientMode("readonly") == ClientMode.READONLY
    assert ClientMode("readwrite") == ClientMode.READWRITE


def test_client_mode_invalid_value() -> None:
    """Test ClientMode raises on invalid value."""
    import pytest

    with pytest.raises(ValueError):
        ClientMode("invalid")


def test_upsert_action_values() -> None:
    assert UpsertAction.CREATED == "created"
    assert UpsertAction.UPDATED == "updated"
    assert UpsertAction.UNCHANGED == "unchanged"
    assert UpsertAction.WOULD_CREATE == "would_create"
    assert UpsertAction.WOULD_UPDATE == "would_update"


def test_upsert_result_is_frozen() -> None:
    result = UpsertResult(
        action=UpsertAction.UNCHANGED, time=Time(id=1), changed_fields=frozenset()
    )
    assert result.action is UpsertAction.UNCHANGED
    assert result.time is not None and result.time.id == 1
    assert result.changed_fields == frozenset()
    with pytest.raises(FrozenInstanceError):
        result.action = UpsertAction.CREATED  # type: ignore[misc]
