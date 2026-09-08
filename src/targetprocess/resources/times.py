"""Time resource manager."""

from datetime import date, datetime, timedelta, tzinfo
from math import isfinite
from typing import Any

from targetprocess.exceptions import AmbiguousMatchError
from targetprocess.models import Time, format_tp_date
from targetprocess.resources.base import BaseResource
from targetprocess.types import UpsertAction, UpsertResult

# Fields the upsert comparison reads, so find_for_day always hydrates them.
_DEFAULT_INCLUDE = ["Id", "Date", "Spent", "Remain", "IsEstimation", "Description"]

# The only fields upsert ever writes to an existing entry, mapped from model
# field name to TP API field name. Everything else (Assignable, User, Date,
# Project, Role) is identity: changing one would re-key the entry, not sync it.
_MUTABLE_FIELDS = {
    "spent": "Spent",
    "description": "Description",
    "remain": "Remain",
    "is_estimation": "IsEstimation",
}


def _resolve_day(when: datetime, tz: tzinfo | None) -> tuple[date, tzinfo]:
    """Resolve the calendar day a time entry is keyed on.

    Args:
        when: Timezone-aware instant the work was logged at.
        tz: Timezone that defines the day, or None to use ``when``'s own.

    Returns:
        The calendar day and the timezone it was derived in.

    Raises:
        ValueError: ``when`` is naive, so no day can be derived.
    """
    when_tz = when.tzinfo
    if when_tz is None or when.utcoffset() is None:
        raise ValueError("upsert requires a timezone-aware 'when'")
    resolved: tzinfo = tz if tz is not None else when_tz
    return when.astimezone(resolved).date(), resolved


def _require_positive_int(name: str, value: int) -> None:
    """Ensure a value used to build the TP ``where`` filter is a genuine positive int.

    Type annotations are not enforced at runtime, so a caller forwarding an
    untrusted value (an HTTP parameter, a CSV cell, a webhook field) could
    pass a string or a negative/zero value that alters the interpolated
    filter rather than merely selecting the wrong entry. ``bool`` is a
    subclass of ``int`` in Python (``isinstance(True, int)`` is ``True``), so
    it is rejected explicitly via an exact-type check rather than accepted as
    0/1.

    Args:
        name: Parameter name, for the error message.
        value: Value to check.

    Raises:
        ValueError: ``value`` is not a genuine positive ``int``.
    """
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive int, got {value!r}")


def _validate_duration(name: str, value: float) -> None:
    """Ensure a duration value is a finite, non-boolean, non-negative number.

    Type annotations are not enforced at runtime, so a caller forwarding an
    untrusted value could pass something that slips past a bare ``< 0``
    check: ``bool`` is a subclass of ``int`` in Python
    (``isinstance(True, int)`` is ``True``), so ``False < 0`` is ``False``
    and a bool would otherwise be accepted and JSON-encode as ``true``/
    ``false`` rather than a number; ``float("nan")`` fails every comparison,
    including ``< 0``; and ``float("inf")`` is ``>= 0`` and would otherwise
    be forwarded to TP as-is.

    Args:
        name: Parameter name, for the error message.
        value: Value to check.

    Raises:
        ValueError: ``value`` is not a finite, non-boolean number ``>= 0``.
    """
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")


def _supplied_mutable_fields(
    *,
    spent: float,
    description: str | None,
    remain: float | None,
    is_estimation: bool | None,
) -> dict[str, Any]:
    """Collect the mutable fields the caller actually supplied.

    An omitted field is not synced, so a caller passing only ``spent`` leaves
    a drifted description alone.

    Args:
        spent: Hours spent. Always supplied.
        description: Free-text description, or None if not supplied.
        remain: Hours remaining, or None if not supplied.
        is_estimation: Estimation flag, or None if not supplied.

    Returns:
        Model field name to value, for every supplied field.

    Raises:
        ValueError: ``spent`` or ``remain`` is not a finite, non-boolean
            number ``>= 0``. Checked here, ahead of ``find_for_day`` and any
            create/update, so a bad value is rejected before a request is
            sent - not written and then hit as a confusing ``ParseError`` on
            the next read-back (``Time.spent``/``Time.remain`` carry
            ``ge=0``).
    """
    _validate_duration("spent", spent)
    if remain is not None:
        _validate_duration("remain", remain)
    supplied: dict[str, Any] = {"spent": spent}
    if description is not None:
        # Entity sets str_strip_whitespace=True, so TP's value is read back
        # stripped. Strip on the way in too, or a padded description differs
        # on every run and updates repeatedly instead of converging.
        supplied["description"] = description.strip()
    if remain is not None:
        supplied["remain"] = remain
    if is_estimation is not None:
        supplied["is_estimation"] = is_estimation
    return supplied


def _create_payload(
    *,
    assignable_id: int,
    user_id: int,
    when: datetime,
    supplied: dict[str, Any],
    project_id: int | None,
    role_id: int | None,
) -> dict[str, Any]:
    """Build the API field set for a Time create.

    Args:
        assignable_id: Assignable (work item) ID.
        user_id: User the time is logged for.
        when: Timezone-aware instant, encoded to TP's wire format.
        supplied: Mutable fields as returned by ``_supplied_mutable_fields``.
        project_id: Project ID, or None to let TP derive it from the Assignable.
        role_id: Role ID, or None to omit.

    Returns:
        API-shaped field set for ``BaseResource.create``.
    """
    payload: dict[str, Any] = {
        "Assignable": {"Id": assignable_id},
        "User": {"Id": user_id},
        "Date": format_tp_date(when),
    }
    payload.update({_MUTABLE_FIELDS[name]: value for name, value in supplied.items()})
    if project_id is not None:
        payload["Project"] = {"Id": project_id}
    if role_id is not None:
        payload["Role"] = {"Id": role_id}
    return payload


class TimesResource(BaseResource[Time]):
    """Resource manager for Time entities.

    Provides type-safe CRUD operations for time entries.

    Example:
        client = TargetProcessClient(...)
        entry = await client.times.get(123)
        async for entry in client.times.list(limit=10):
            print(entry.spent)
    """

    entity_type = "Time"
    model_class = Time

    async def find_for_day(
        self,
        *,
        assignable_id: int,
        user_id: int,
        day: date,
        tz: tzinfo,
        include: list[str] | None = None,
    ) -> list[Time]:
        """Return the time entries logged against an assignable by a user on one day.

        TP stores ``Date`` as the instant supplied and normalises nothing, so
        a ``Date eq`` filter is unreliable at a day boundary. The server-side
        window is therefore a day wider on each side than ``day``, and the
        exact-day decision is made here by projecting each stored instant into
        ``tz``. Which day an instant falls on is a function of ``tz``, so read
        in the same zone the entries were written in — a different zone
        resolves a near-midnight entry onto the adjacent day and misses it
        (see SPEC.md's "Time upsert semantics" for the full rationale).

        Args:
            assignable_id: Assignable (work item) ID.
            user_id: User ID the entries belong to.
            day: Calendar day, interpreted in ``tz``.
            tz: Timezone that defines the day boundaries.
            include: Fields to hydrate. Defaults to the set the upsert
                comparison reads. ``"Date"`` is always requested in addition
                to whatever is supplied — appended if missing, otherwise
                left in the caller's position — since the client-side day
                filter skips every entry whose ``date`` is ``None``.

        Returns:
            Matching entries, in the order TP returned them.

        Raises:
            ValueError: ``assignable_id`` or ``user_id`` is not a genuine
                positive ``int`` (``bool`` included - see
                ``_require_positive_int``).
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        _require_positive_int("assignable_id", assignable_id)
        _require_positive_int("user_id", user_id)
        where = (
            f"(Assignable.Id eq {assignable_id})"
            f"and(User.Id eq {user_id})"
            f"and(Date gte '{day - timedelta(days=1)}')"
            f"and(Date lt '{day + timedelta(days=2)}')"
        )
        resolved_include = (
            list(_DEFAULT_INCLUDE) if include is None else list(dict.fromkeys([*include, "Date"]))
        )
        return [
            entry
            async for entry in self.list(where=where, include=resolved_include)
            if entry.date is not None and entry.date.astimezone(tz).date() == day
        ]

    async def upsert(
        self,
        *,
        assignable_id: int,
        user_id: int,
        when: datetime,
        spent: float,
        description: str | None = None,
        remain: float | None = None,
        is_estimation: bool | None = None,
        project_id: int | None = None,
        role_id: int | None = None,
        tz: tzinfo | None = None,
        dry_run: bool = False,
    ) -> UpsertResult:
        """Idempotently sync a time entry keyed on ``(assignable, user, day)``.

        TP has no upsert primitive, so this finds the day's entry and then
        creates or updates it. ``spent`` is excluded from the key, so a
        changed duration updates the existing entry rather than adding a
        duplicate — which also makes the call self-healing after a timeout
        that committed a write the caller never saw the response to.

        This is find-then-create with no locking, and TP has no unique
        constraint on ``(assignable, user, day)``, so two concurrent calls
        for the same key can both find no match and both create — callers
        must serialise per key. A resulting duplicate wedges that day: every
        later call raises :class:`AmbiguousMatchError` until a human removes
        one of the entries.

        Only the fields the caller supplies are compared and written. Passing
        just ``spent`` syncs only the duration; passing ``description`` as
        well makes description drift propagate too.

        ``spent`` is sent as given and compared exactly — no rounding is
        applied here. If you pass more decimal places than your instance
        stores, TP quantises on write and every subsequent call will see a
        difference and update again; quantise to your instance's precision
        before calling.

        Args:
            assignable_id: Assignable (work item) ID.
            user_id: User the time is logged for.
            when: Timezone-aware instant the work was logged at.
            spent: Hours spent.
            description: Free-text description. Omitted fields are not synced.
                Stripped before comparing and writing, matching the read-back
                value (``Entity`` sets ``str_strip_whitespace=True``), so a
                padded description converges instead of updating forever. A
                whitespace-only description strips to ``""``; if TP reads
                that back as null rather than an empty string, the comparison
                never converges and every call updates again — the same
                non-convergence class the padding case is guarded against.
            remain: Hours remaining.
            is_estimation: Whether the entry records an estimate.
            project_id: Project ID. Only used when creating a new entry
                (omit to let TP derive it from the Assignable); ignored when
                a matching entry already exists, since Project is identity.
            role_id: Role ID. Only used when creating a new entry; ignored
                when a matching entry already exists, since Role is identity.
            tz: Timezone that defines the day. Defaults to ``when``'s own.
                TP stores ``Date`` as the instant supplied and normalises
                nothing, so which day an entry falls on depends entirely on
                ``tz`` — read in the same zone the entries were written in.
                A different zone resolves a near-midnight entry onto the
                adjacent day, which makes this method miss it and create a
                duplicate.
            dry_run: Report the planned action without writing anything.

        Returns:
            The action taken (or planned), the entry, and the mutable fields
            synced.

        Raises:
            ValueError: ``when`` is naive; ``spent``/``remain`` is not a
                finite, non-boolean number ``>= 0``; or
                ``assignable_id``/``user_id`` is not a genuine positive
                ``int`` (``bool`` included).
            AmbiguousMatchError: More than one entry matches the key.
            ReadOnlyViolation: A write was needed on a READONLY client.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        day, resolved_tz = _resolve_day(when, tz)
        supplied = _supplied_mutable_fields(
            spent=spent, description=description, remain=remain, is_estimation=is_estimation
        )
        matches = await self.find_for_day(
            assignable_id=assignable_id, user_id=user_id, day=day, tz=resolved_tz
        )
        if len(matches) > 1:
            raise AmbiguousMatchError(
                f"{len(matches)} Time entries already match assignable {assignable_id} / "
                f"user {user_id} on {day.isoformat()}",
                assignable_id=assignable_id,
                user_id=user_id,
                day=day,
                count=len(matches),
            )

        if not matches:
            changed = frozenset(supplied)
            if dry_run:
                return UpsertResult(
                    action=UpsertAction.WOULD_CREATE, time=None, changed_fields=changed
                )
            created = await self.create(
                **_create_payload(
                    assignable_id=assignable_id,
                    user_id=user_id,
                    # Encode in the key timezone, not when's own offset. The
                    # instant is identical either way and TP re-renders Date
                    # in its own zone on read, so this changes nothing TP
                    # stores; it keeps the wire offset consistent with the
                    # zone the day was resolved in.
                    when=when.astimezone(resolved_tz),
                    supplied=supplied,
                    project_id=project_id,
                    role_id=role_id,
                )
            )
            return UpsertResult(action=UpsertAction.CREATED, time=created, changed_fields=changed)

        existing = matches[0]
        diff = {name: value for name, value in supplied.items() if getattr(existing, name) != value}
        if not diff:
            return UpsertResult(
                action=UpsertAction.UNCHANGED, time=existing, changed_fields=frozenset()
            )
        changed = frozenset(diff)
        if dry_run:
            return UpsertResult(
                action=UpsertAction.WOULD_UPDATE, time=existing, changed_fields=changed
            )
        updated = await self.update(
            existing.id, **{_MUTABLE_FIELDS[name]: value for name, value in diff.items()}
        )
        return UpsertResult(action=UpsertAction.UPDATED, time=updated, changed_fields=changed)
