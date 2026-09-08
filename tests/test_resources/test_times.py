"""Tests for TimesResource."""

from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess.client import TargetProcessClient
from targetprocess.exceptions import AmbiguousMatchError, ReadOnlyViolation
from targetprocess.models import Time
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.times import TimesResource
from targetprocess.types import ClientMode, UpsertAction


def _resource(mode: ClientMode = ClientMode.READWRITE) -> tuple[TimesResource, Mock, AsyncMock]:
    client = Mock(spec=TargetProcessClient)
    client.mode = mode
    client._check_write_permission = Mock(spec=TargetProcessClient._check_write_permission)
    handler = AsyncMock(spec=RequestHandler)
    return TimesResource(client, handler), client, handler


@pytest.mark.asyncio
async def test_times_resource_entity_type() -> None:
    resource, _, _ = _resource()
    assert resource.entity_type == "Time"
    assert resource.model_class == Time


@pytest.mark.asyncio
async def test_times_inherits_crud() -> None:
    resource, _, _ = _resource()
    for method in ("get", "list", "create", "update", "delete"):
        assert hasattr(resource, method)


def _stub_list(handler: AsyncMock, items: list[dict]) -> list[dict]:
    """Make handler.list an async generator; return a list captured calls append to."""
    calls: list[dict] = []

    async def fake_list(entity_type, **kwargs):
        calls.append({"entity_type": entity_type, **kwargs})
        for item in items:
            yield item

    handler.list = fake_list
    return calls


SAST = timezone(timedelta(hours=2))


@pytest.mark.asyncio
async def test_find_for_day_builds_widened_window() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    await resource.find_for_day(assignable_id=51383, user_id=1, day=date(2026, 8, 9), tz=SAST)

    assert len(calls) == 1
    assert calls[0]["entity_type"] == "Time"
    assert calls[0]["where"] == (
        "(Assignable.Id eq 51383)and(User.Id eq 1)"
        "and(Date gte '2026-08-08')and(Date lt '2026-08-11')"
    )


@pytest.mark.asyncio
async def test_find_for_day_default_include_covers_compared_fields() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    await resource.find_for_day(assignable_id=1, user_id=1, day=date(2026, 8, 9), tz=SAST)

    assert calls[0]["include"] == [
        "Id",
        "Date",
        "Spent",
        "Remain",
        "IsEstimation",
        "Description",
    ]


@pytest.mark.asyncio
async def test_find_for_day_honours_explicit_include() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    await resource.find_for_day(
        assignable_id=1, user_id=1, day=date(2026, 8, 9), tz=SAST, include=["Id"]
    )

    assert calls[0]["include"] == ["Id", "Date"]


@pytest.mark.asyncio
async def test_find_for_day_appends_date_to_explicit_include_missing_it() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(
        handler, [{"Id": 1, "Date": "/Date(1786269600000+0200)/", "Project": {"Id": 7}}]
    )

    found = await resource.find_for_day(
        assignable_id=1, user_id=1, day=date(2026, 8, 9), tz=SAST, include=["Project"]
    )

    assert calls[0]["include"] == ["Project", "Date"]
    assert [t.id for t in found] == [1]


@pytest.mark.asyncio
async def test_find_for_day_does_not_duplicate_an_already_included_date() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    await resource.find_for_day(
        assignable_id=1, user_id=1, day=date(2026, 8, 9), tz=SAST, include=["Date", "Spent"]
    )

    assert calls[0]["include"] == ["Date", "Spent"]


@pytest.mark.asyncio
async def test_find_for_day_filters_window_down_to_the_exact_day() -> None:
    resource, _, handler = _resource()
    # 2026-08-09 in SAST spans 2026-08-08T22:00Z to 2026-08-09T22:00Z.
    _stub_list(
        handler,
        [
            {"Id": 1, "Date": "/Date(1786269600000+0200)/"},  # 2026-08-09T12:00+02:00
            {"Id": 2, "Date": "/Date(1786183200000+0200)/"},  # 2026-08-08T12:00+02:00
            {"Id": 3, "Date": "/Date(1786356000000+0200)/"},  # 2026-08-10T12:00+02:00
        ],
    )

    found = await resource.find_for_day(assignable_id=1, user_id=1, day=date(2026, 8, 9), tz=SAST)

    assert [t.id for t in found] == [1]


@pytest.mark.asyncio
async def test_find_for_day_projects_into_the_supplied_tz() -> None:
    resource, _, handler = _resource()
    # 2026-08-09T23:30+02:00 is 21:30Z — the same instant is 2026-08-09 in SAST
    # but also 2026-08-09 in UTC; 2026-08-10T00:30+02:00 (22:30Z) differs.
    _stub_list(
        handler,
        [
            {"Id": 1, "Date": "/Date(1786314600000+0200)/"},  # 2026-08-10T00:30+02:00
        ],
    )

    in_sast = await resource.find_for_day(
        assignable_id=1, user_id=1, day=date(2026, 8, 10), tz=SAST
    )
    in_utc = await resource.find_for_day(assignable_id=1, user_id=1, day=date(2026, 8, 10), tz=UTC)

    assert [t.id for t in in_sast] == [1]
    assert in_utc == []


@pytest.mark.asyncio
async def test_find_for_day_skips_entries_with_no_date() -> None:
    resource, _, handler = _resource()
    _stub_list(handler, [{"Id": 1}])

    found = await resource.find_for_day(assignable_id=1, user_id=1, day=date(2026, 8, 9), tz=SAST)

    assert found == []


@pytest.mark.asyncio
async def test_find_for_day_resolves_the_day_in_the_projection_tz() -> None:
    # Which calendar day an entry falls on is a property of the tz it is
    # projected into, not of TP - TP stores Date exactly as its writer
    # submitted it (see SPEC.md "Time dates"). The wire value below is real,
    # taken from a live instance: /Date(1786060800000+0200)/ decodes to
    # 2026-08-07T00:00:00Z, so it resolves onto 2026-08-07 in UTC and in a
    # zone east of it, but onto 2026-08-06 four hours west - where a reader
    # misses it and upsert would create a duplicate. Read in the zone the
    # entries were written in.
    resource, _, handler = _resource()
    _stub_list(handler, [{"Id": 42027, "Date": "/Date(1786060800000+0200)/"}])
    west_of_utc = timezone(timedelta(hours=-4))

    east_of_utc = await resource.find_for_day(
        assignable_id=68395, user_id=1, day=date(2026, 8, 7), tz=SAST
    )
    at_utc = await resource.find_for_day(
        assignable_id=68395, user_id=1, day=date(2026, 8, 7), tz=UTC
    )
    missed = await resource.find_for_day(
        assignable_id=68395, user_id=1, day=date(2026, 8, 7), tz=west_of_utc
    )

    assert [t.id for t in east_of_utc] == [42027]
    assert [t.id for t in at_utc] == [42027]
    assert missed == []


@pytest.mark.asyncio
async def test_find_for_day_rejects_a_string_that_would_alter_the_filter() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    with pytest.raises(ValueError, match="assignable_id"):
        await resource.find_for_day(
            assignable_id="1) or (1 eq 1",  # type: ignore[arg-type]
            user_id=1,
            day=date(2026, 8, 9),
            tz=SAST,
        )

    assert calls == []


@pytest.mark.asyncio
async def test_find_for_day_rejects_negative_id() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    with pytest.raises(ValueError, match="assignable_id"):
        await resource.find_for_day(assignable_id=-1, user_id=1, day=date(2026, 8, 9), tz=SAST)

    assert calls == []


@pytest.mark.asyncio
async def test_find_for_day_rejects_zero_id() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    with pytest.raises(ValueError, match="user_id"):
        await resource.find_for_day(assignable_id=1, user_id=0, day=date(2026, 8, 9), tz=SAST)

    assert calls == []


@pytest.mark.asyncio
async def test_find_for_day_rejects_bool_id() -> None:
    # isinstance(True, int) is True in Python, so this must be rejected by an
    # explicit type check rather than accepted as 1.
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    with pytest.raises(ValueError, match="user_id"):
        await resource.find_for_day(assignable_id=1, user_id=True, day=date(2026, 8, 9), tz=SAST)

    assert calls == []


WHEN = datetime(2026, 8, 9, 14, 0, tzinfo=SAST)


@pytest.mark.asyncio
async def test_upsert_creates_when_no_match() -> None:
    resource, _, handler = _resource()
    _stub_list(handler, [])
    handler.create.return_value = {"Id": 42, "Spent": 2.5}

    result = await resource.upsert(
        assignable_id=51383, user_id=1, when=WHEN, spent=2.5, description="Work"
    )

    assert result.action is UpsertAction.CREATED
    assert result.time is not None and result.time.id == 42
    assert result.changed_fields == frozenset({"spent", "description"})
    handler.create.assert_awaited_once()
    entity_type, fields = handler.create.await_args.args
    assert entity_type == "Time"
    assert fields["Assignable"] == {"Id": 51383}
    assert fields["User"] == {"Id": 1}
    assert fields["Date"] == "/Date(1786276800000+0200)/"  # == format_tp_date(WHEN)
    assert fields["Spent"] == 2.5
    assert fields["Description"] == "Work"
    assert "Project" not in fields
    assert "Role" not in fields
    assert "Remain" not in fields
    assert "IsEstimation" not in fields


@pytest.mark.asyncio
async def test_upsert_create_includes_optional_refs_when_supplied() -> None:
    resource, _, handler = _resource()
    _stub_list(handler, [])
    handler.create.return_value = {"Id": 42}

    result = await resource.upsert(
        assignable_id=1,
        user_id=2,
        when=WHEN,
        spent=1.0,
        remain=0.5,
        is_estimation=True,
        project_id=300,
        role_id=20,
    )

    assert result.action is UpsertAction.CREATED
    assert result.changed_fields == frozenset({"spent", "remain", "is_estimation"})
    _, fields = handler.create.await_args.args
    assert fields["Project"] == {"Id": 300}
    assert fields["Role"] == {"Id": 20}
    assert fields["Remain"] == 0.5
    assert fields["IsEstimation"] is True
    assert "Description" not in fields


@pytest.mark.asyncio
async def test_upsert_updates_only_the_differing_fields() -> None:
    resource, _, handler = _resource()
    _stub_list(
        handler,
        [
            {
                "Id": 42,
                "Date": "/Date(1786269600000+0200)/",
                "Spent": 1.0,
                "Description": "Same",
            }
        ],
    )
    handler.update.return_value = {"Id": 42, "Spent": 2.5}

    result = await resource.upsert(
        assignable_id=1, user_id=2, when=WHEN, spent=2.5, description="Same"
    )

    assert result.action is UpsertAction.UPDATED
    assert result.changed_fields == frozenset({"spent"})
    handler.update.assert_awaited_once_with("Time", 42, {"Spent": 2.5})


@pytest.mark.asyncio
async def test_upsert_updates_remain_and_is_estimation_by_name() -> None:
    resource, _, handler = _resource()
    _stub_list(
        handler,
        [
            {
                "Id": 42,
                "Date": "/Date(1786269600000+0200)/",
                "Spent": 1.0,
                "Remain": 0.5,
                "IsEstimation": False,
            }
        ],
    )
    handler.update.return_value = {"Id": 42, "Remain": 1.5}

    result = await resource.upsert(
        assignable_id=1,
        user_id=2,
        when=WHEN,
        spent=1.0,
        remain=1.5,
        is_estimation=False,
    )

    assert result.changed_fields == frozenset({"remain"})
    handler.update.assert_awaited_once_with("Time", 42, {"Remain": 1.5})


@pytest.mark.asyncio
async def test_upsert_unchanged_when_every_supplied_field_matches() -> None:
    resource, _, handler = _resource()
    _stub_list(
        handler,
        [{"Id": 42, "Date": "/Date(1786269600000+0200)/", "Spent": 2.5, "Description": "Same"}],
    )

    result = await resource.upsert(
        assignable_id=1, user_id=2, when=WHEN, spent=2.5, description="Same"
    )

    assert result.action is UpsertAction.UNCHANGED
    assert result.changed_fields == frozenset()
    assert result.time is not None and result.time.id == 42
    handler.create.assert_not_awaited()
    handler.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_ignores_fields_the_caller_did_not_supply() -> None:
    resource, _, handler = _resource()
    # Description differs, but the caller did not supply one, so it is not synced.
    _stub_list(
        handler,
        [{"Id": 42, "Date": "/Date(1786269600000+0200)/", "Spent": 2.5, "Description": "Drifted"}],
    )

    result = await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=2.5)

    assert result.action is UpsertAction.UNCHANGED
    handler.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_strips_description_before_comparing_and_writing() -> None:
    resource, _, handler = _resource()
    # Entity's str_strip_whitespace=True means a stored "Work" reads back
    # stripped; without stripping the supplied value too, "Work " would
    # never equal "Work" and every call would update again.
    _stub_list(
        handler,
        [{"Id": 42, "Date": "/Date(1786269600000+0200)/", "Spent": 1.0, "Description": "Work"}],
    )

    result = await resource.upsert(
        assignable_id=1, user_id=2, when=WHEN, spent=1.0, description="Work "
    )

    assert result.action is UpsertAction.UNCHANGED
    handler.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_dry_run_would_create_writes_nothing() -> None:
    resource, _, handler = _resource()
    _stub_list(handler, [])

    result = await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=2.5, dry_run=True)

    assert result.action is UpsertAction.WOULD_CREATE
    assert result.time is None
    assert result.changed_fields == frozenset({"spent"})
    handler.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_dry_run_would_update_writes_nothing() -> None:
    resource, _, handler = _resource()
    _stub_list(handler, [{"Id": 42, "Date": "/Date(1786269600000+0200)/", "Spent": 1.0}])

    result = await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=2.5, dry_run=True)

    assert result.action is UpsertAction.WOULD_UPDATE
    assert result.time is not None and result.time.id == 42
    assert result.changed_fields == frozenset({"spent"})
    handler.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_raises_on_ambiguous_match() -> None:
    resource, _, handler = _resource()
    _stub_list(
        handler,
        [
            {"Id": 1, "Date": "/Date(1786269600000+0200)/", "Spent": 1.0},
            {"Id": 2, "Date": "/Date(1786269600000+0200)/", "Spent": 1.0},
        ],
    )

    with pytest.raises(AmbiguousMatchError) as excinfo:
        await resource.upsert(assignable_id=51383, user_id=7, when=WHEN, spent=2.5)

    assert excinfo.value.count == 2
    assert excinfo.value.assignable_id == 51383
    assert excinfo.value.user_id == 7
    assert excinfo.value.day == date(2026, 8, 9)
    handler.create.assert_not_awaited()
    handler.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_rejects_naive_when() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    with pytest.raises(ValueError, match="timezone-aware"):
        await resource.upsert(
            assignable_id=1, user_id=2, when=datetime(2026, 8, 9, 14, 0), spent=1.0
        )

    assert calls == []


@pytest.mark.asyncio
async def test_upsert_rejects_negative_spent() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    with pytest.raises(ValueError, match="spent"):
        await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=-1.0)

    assert calls == []


@pytest.mark.asyncio
async def test_upsert_rejects_negative_remain() -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    with pytest.raises(ValueError, match="remain"):
        await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=1.0, remain=-1.0)

    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), True, False],
    ids=["nan", "inf", "-inf", "True", "False"],
)
async def test_upsert_rejects_non_finite_or_boolean_spent(value: float) -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    with pytest.raises(ValueError, match="spent"):
        await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=value)

    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), True, False],
    ids=["nan", "inf", "-inf", "True", "False"],
)
async def test_upsert_rejects_non_finite_or_boolean_remain(value: float) -> None:
    resource, _, handler = _resource()
    calls = _stub_list(handler, [])

    with pytest.raises(ValueError, match="remain"):
        await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=1.0, remain=value)

    assert calls == []


@pytest.mark.asyncio
async def test_upsert_tz_overrides_the_datetime_offset() -> None:
    resource, _, handler = _resource()
    # This entry sits at 2026-08-09T12:00 UTC (WHEN's instant), which is only
    # inside the 2026-08-09 UTC day — not the 2026-08-10 SAST day `when`
    # itself falls on — so a match here proves `tz`, not `when`'s own
    # offset, drove both the query window and the exact-day filter.
    calls = _stub_list(handler, [{"Id": 42, "Date": "/Date(1786276800000+0200)/", "Spent": 0.5}])
    # 2026-08-10T00:30+02:00 is 2026-08-09 in UTC.
    when = datetime(2026, 8, 10, 0, 30, tzinfo=SAST)

    result = await resource.upsert(
        assignable_id=1, user_id=2, when=when, spent=1.0, tz=UTC, dry_run=True
    )

    assert "(Date gte '2026-08-08')" in calls[0]["where"]
    assert "(Date lt '2026-08-11')" in calls[0]["where"]
    assert result.action is UpsertAction.WOULD_UPDATE
    assert result.time is not None and result.time.id == 42


@pytest.mark.asyncio
async def test_upsert_create_encodes_when_in_the_key_timezone() -> None:
    # WHEN is 2026-08-09T14:00+02:00 (SAST), i.e. 2026-08-09T12:00:00Z. With
    # no tz override, day is resolved in WHEN's own offset and
    # format_tp_date(WHEN) == "/Date(1786276800000+0200)/" (see
    # test_upsert_creates_when_no_match). Overriding tz=UTC must instead
    # encode the same instant under UTC's offset: same epoch milliseconds,
    # "+0000" suffix. Observed via a throwaway snippet:
    #   format_tp_date(WHEN.astimezone(UTC)) == "/Date(1786276800000+0000)/"
    resource, _, handler = _resource()
    _stub_list(handler, [])
    handler.create.return_value = {"Id": 99, "Spent": 1.0}

    result = await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=1.0, tz=UTC)

    assert result.action is UpsertAction.CREATED
    _, fields = handler.create.await_args.args
    assert fields["Date"] == "/Date(1786276800000+0000)/"


@pytest.mark.asyncio
async def test_upsert_readonly_raises_on_a_real_write() -> None:
    resource, client, handler = _resource(ClientMode.READONLY)
    client._check_write_permission = Mock(
        spec=TargetProcessClient._check_write_permission,
        side_effect=ReadOnlyViolation("create", "Time"),
    )
    _stub_list(handler, [])

    with pytest.raises(ReadOnlyViolation):
        await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=1.0)


@pytest.mark.asyncio
async def test_upsert_readonly_allows_dry_run_and_unchanged() -> None:
    resource, client, handler = _resource(ClientMode.READONLY)
    client._check_write_permission = Mock(
        spec=TargetProcessClient._check_write_permission,
        side_effect=ReadOnlyViolation("create", "Time"),
    )
    _stub_list(handler, [{"Id": 42, "Date": "/Date(1786269600000+0200)/", "Spent": 1.0}])

    planned = await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=2.5, dry_run=True)
    unchanged = await resource.upsert(assignable_id=1, user_id=2, when=WHEN, spent=1.0)

    assert planned.action is UpsertAction.WOULD_UPDATE
    assert unchanged.action is UpsertAction.UNCHANGED
    handler.create.assert_not_awaited()
    handler.update.assert_not_awaited()
