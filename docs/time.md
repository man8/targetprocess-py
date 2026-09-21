# Logging time

How to record time against a work item with `client.times`, including the
idempotent `upsert` and the custom-activity variant. Split out of
[the usage guide](USAGE.md), which carries the rest of the surface and links
here.

`client.times` provides the usual CRUD surface, plus `upsert` — an idempotent
sync keyed on `(assignable, user, day)`. Use it when a source system is the
truth and the same day may be synced repeatedly: a second run updates the
existing entry rather than adding a duplicate.

```python
from datetime import datetime, timedelta, timezone

sast = timezone(timedelta(hours=2))

result = await client.times.upsert(
    assignable_id=51383,
    user_id=1,
    when=datetime(2026, 8, 9, 14, 0, tzinfo=sast),
    spent=2.5,
    description="Investigated the failing sync",
)
print(result.action, sorted(result.changed_fields))
```

`when` must be timezone-aware — it is what defines which calendar day the
entry is keyed on. Pass `tz=` to key on a different timezone from the one
`when` carries.

Choose `tz` carefully, and keep it the same for every call that touches a
given day: it defines the calendar day an entry is matched against, and TP
stores the instant you send rather than normalising it to a day boundary.
Read in the same zone you wrote in — projecting into a different zone
resolves a near-midnight entry onto the adjacent day, so `upsert` misses it
and creates a duplicate. See
[SPEC.md](../SPEC.md#time-upsert-semantics) for the full rationale.

Only the fields you supply are compared and written, so the call above syncs
the description too, while omitting `description` would leave a drifted one
alone. A supplied `description` is stripped of leading/trailing whitespace
before comparing and writing — a stored description always reads back
stripped, so an unstripped value would otherwise look changed on every call.

Plan a run without writing anything — this works on a READONLY client:

```python
planned = await client.times.upsert(
    assignable_id=51383,
    user_id=1,
    when=datetime(2026, 8, 9, 14, 0, tzinfo=sast),
    spent=2.5,
    dry_run=True,
)
assert planned.action in {"would_create", "would_update", "unchanged"}
```

To read a day's entries without syncing, use `find_for_day`:

```python
from datetime import date

entries = await client.times.find_for_day(
    assignable_id=51383, user_id=1, day=date(2026, 8, 9), tz=sast
)
```

If the day already holds more than one entry for that assignable and user,
`upsert` raises `AmbiguousMatchError` rather than guessing which to update.

## Time against a custom activity

`upsert` and `find_for_day` key on an assignable, so an entry logged against a
custom activity goes through the ordinary `create` and `list`. Send
`CustomActivity` and leave `Assignable` out of the payload altogether - omit
the key rather than sending it as `None`:

```python
from targetprocess_py.models import format_tp_date

entry = await client.times.create(
    CustomActivity={"Id": 42},
    User={"Id": 7},
    Date=format_tp_date(datetime(2026, 8, 9, 9, 0, tzinfo=sast)),
    Spent=0.5,
    Description="Weekly planning",
)
```

The entry reads back with a null `assignable` and its `custom_activity`
back-reference set (see [SPEC.md](../SPEC.md#models)). To read a day's entries
against an activity, filter on the window `find_for_day` uses, a day wider on
each side, then keep the exact day by projecting each `date` into the zone the
entries were written in:

```python
day = date(2026, 8, 9)
where = (
    "(CustomActivity.Id eq 42) and (User.Id eq 7)"
    f" and (Date gte '{day - timedelta(days=1)}')"
    f" and (Date lt '{day + timedelta(days=2)}')"
)
entries = [
    entry
    async for entry in client.times.list(where=where)
    if entry.date is not None and entry.date.astimezone(sast).date() == day
]
```
