"""Compare the fields a write requested with an independent re-read of the entity.

The comparison behind ``update(..., verify=True)``. Each requested field is
matched against the raw re-read, by these rules in order:

- Keys match case-insensitively, as the ``Id`` guards on the bulk path do.
- A requested ``CustomFields`` sequence (any but a string, bytes or
  bytearray) is routed entry by entry before any other rule applies, each
  entry matched by name (case-insensitively). A cleared entry (``Value``
  ``None``) matches an observed null, ``""``, ``False`` or ``0`` - each is
  TP's empty state for some field type, so accepting the set never masks a
  failed clear. Any other value is compared by the rules below, and an entry
  of that name missing from the re-read is a mismatch keyed
  ``CustomFields[<name>]``. An entry that is not a mapping carrying a string
  ``Name`` cannot be looked up, so it is a mismatch too, keyed by its
  zero-based position (``CustomFields[#<position>]``) and observed as
  ``VerificationError.ABSENT``.
- A requested key the re-read does not carry at all is a mismatch, observed
  as ``VerificationError.ABSENT`` - unless the request was ``None``, which an
  absent key satisfies. A field TargetProcess never returns (``Password``)
  can therefore never verify.
- A requested ``None`` matches an observed null.
- A requested mapping carrying an ``Id`` is a reference, and matches an
  observed mapping with an equal ``Id``; the rest of the observed reference
  (``Name``, ``NumericPriority``, ...) is ignored.
- Numbers compare numerically, so ``3`` matches ``3.0``; a boolean is not a
  number here, so ``True`` does not match ``1``, and a string is never parsed
  as a number, so ``"3"`` does not match ``3``.
- Two TargetProcess wire dates (``/Date(ms±HHMM)/``) compare on the instant
  they denote, since the offset echoed can differ from the one sent.
- Other strings compare with surrounding whitespace stripped, as the models
  store them.
- Anything else, other lists included, compares by equality.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, TypeGuard

from targetprocess_py._dates import parse_tp_date
from targetprocess_py.exceptions import VerificationError

ABSENT = VerificationError.ABSENT

Mismatch = tuple[Any, Any]


def _get(record: Mapping[str, Any], key: str) -> tuple[bool, Any]:
    """Return whether ``record`` carries ``key`` in any casing, and its value if so."""
    wanted = key.casefold()
    for name, value in record.items():
        if isinstance(name, str) and name.casefold() == wanted:
            return True, value
    return False, None


def _reference_id(value: object) -> object:
    """Return the ``Id`` of a reference mapping, or ``None`` when it is not one."""
    if not isinstance(value, Mapping):
        return None
    found, reference_id = _get(value, "Id")
    return reference_id if found else None


def is_entry_sequence(value: object) -> TypeGuard[Sequence[Any]]:
    """Report whether a requested ``CustomFields`` value is compared entry by entry.

    Args:
        value: The ``CustomFields`` value the write sent.

    Returns:
        True for any sequence but a ``str``, ``bytes`` or ``bytearray``; a
        mapping, and anything else, is compared by equality instead.
    """
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)


def custom_field_name(entry: object) -> str | None:
    """Return the ``Name`` a requested ``CustomFields`` entry is looked up by.

    Args:
        entry: One entry of the ``CustomFields`` value the write sent.

    Returns:
        The entry's ``Name``, in whatever casing it is keyed; ``None`` when the
        entry is not a mapping or its name is missing or not a string.
    """
    if not isinstance(entry, Mapping):
        return None
    _, name = _get(entry, "Name")
    return name if isinstance(name, str) else None


def values_match(requested: object, observed: object) -> bool:
    """Report whether one requested wire value is observed, by the module's scalar rules.

    Args:
        requested: The value the write sent.
        observed: The value the re-read carries.

    Returns:
        True when ``observed`` shows ``requested``.
    """
    if requested is None or observed is None:
        return requested is None and observed is None
    requested_id = _reference_id(requested)
    if requested_id is not None:
        return _reference_id(observed) == requested_id
    if isinstance(requested, bool) or isinstance(observed, bool):
        return type(requested) is type(observed) and requested == observed
    if isinstance(requested, int | float) and isinstance(observed, int | float):
        return requested == observed
    if isinstance(requested, str) and isinstance(observed, str):
        requested_date, observed_date = parse_tp_date(requested), parse_tp_date(observed)
        if isinstance(requested_date, datetime) and isinstance(observed_date, datetime):
            return requested_date == observed_date
        return requested.strip() == observed.strip()
    return requested == observed


def custom_field_mismatch(name: str, value: object, observed: object) -> Mismatch | None:
    """Compare one requested custom-field value with a re-read ``CustomFields`` list.

    Args:
        name: The custom field's name, matched case-insensitively.
        value: The value the write sent; ``None`` is a clear, verified by an
            observed null, ``""``, ``False`` or ``0`` - any of TP's empty
            states, regardless of the field's own ``Type``.
        observed: The re-read's ``CustomFields`` list (or whatever it carried).

    Returns:
        ``None`` when the entry verifies; otherwise ``(value, observed value)``,
        with ``ABSENT`` when no entry of that name was read back.
    """
    wanted = name.strip().casefold()
    entries = observed if isinstance(observed, Sequence) and not isinstance(observed, str) else []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        _, entry_name = _get(entry, "Name")
        if isinstance(entry_name, str) and entry_name.strip().casefold() == wanted:
            _, seen = _get(entry, "Value")
            # Each of null, "", False and 0 is TP's empty state for some field
            # type, so accepting the set on a requested clear cannot mask a
            # failed one: for it to pass wrongly the field would already have
            # to be holding an empty value.
            cleared = value is None and seen in (None, "", False, 0)
            return None if cleared or values_match(value, seen) else (value, seen)
    return (value, ABSENT)


def _custom_fields_mismatches(requested: Sequence[Any], observed: object) -> dict[str, Mismatch]:
    """Apply :func:`custom_field_mismatch` to each entry of a requested ``CustomFields`` sequence.

    An entry without a string ``Name`` is reported rather than skipped, keyed
    ``CustomFields[#<position>]`` and observed as ``ABSENT``: nothing could be
    looked up for it, so it cannot have verified.
    """
    mismatches: dict[str, Mismatch] = {}
    for position, entry in enumerate(requested):
        name = custom_field_name(entry)
        if name is None:
            mismatches[f"CustomFields[#{position}]"] = (entry, ABSENT)
            continue
        _, value = _get(entry, "Value")
        mismatch = custom_field_mismatch(name, value, observed)
        if mismatch is not None:
            mismatches[f"CustomFields[{name}]"] = mismatch
    return mismatches


def compare_fields(
    requested: Mapping[str, Any], observed: Mapping[str, Any]
) -> dict[str, Mismatch]:
    """Compare every requested field with the raw re-read of the entity.

    Args:
        requested: The fields the write sent, as wire keys and values.
        observed: The re-read entity's raw JSON object.

    Returns:
        Field -> ``(requested, observed)`` for each field that did not verify;
        empty when every field did.
    """
    mismatches: dict[str, Mismatch] = {}
    for key, value in requested.items():
        present, seen = _get(observed, key)
        if key.casefold() == "customfields" and is_entry_sequence(value):
            mismatches.update(_custom_fields_mismatches(value, seen))
        elif not present:
            if value is not None:
                mismatches[key] = (value, ABSENT)
        elif not values_match(value, seen):
            mismatches[key] = (value, seen)
    return mismatches


def describe(entity_type: str, mismatches: Mapping[int, Mapping[str, Mismatch]]) -> str:
    """Render mismatches as ``<Type> <Id>: <Field>: requested X, observed Y`` clauses.

    Args:
        entity_type: The entity type written.
        mismatches: Entity Id -> field -> ``(requested, observed)``.

    Returns:
        One clause per entity, fields separated by ``; `` within it and
        entities by `` | ``.
    """
    return " | ".join(
        f"{entity_type} {entity_id}: "
        + "; ".join(
            f"{field}: requested {requested!r}, observed {observed!r}"
            for field, (requested, observed) in fields.items()
        )
        for entity_id, fields in mismatches.items()
    )
