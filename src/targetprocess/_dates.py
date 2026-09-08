"""TP ``/Date(ms±HHMM)/`` wire-format date handling.

The public names here (``TPDateTime``, ``parse_tp_date``, ``format_tp_date``)
are re-exported by :mod:`targetprocess.models`, which remains the import
surface callers use.
"""

import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated

from pydantic import BeforeValidator

_TP_DATE_RE = re.compile(r"^/Date\((-?\d+)(?:([+-])(\d{2})(\d{2}))?\)/$")


def parse_tp_date(value: object) -> object:
    """Convert TP's ``/Date(ms±HHMM)/`` wire format to datetime.

    Non-matching values (datetime, ISO strings, None) pass through for
    pydantic's own datetime handling.
    """
    if isinstance(value, str):
        m = _TP_DATE_RE.match(value)
        if m:
            ms = int(m.group(1))
            if m.group(2):
                sign = 1 if m.group(2) == "+" else -1
                tz = timezone(sign * timedelta(hours=int(m.group(3)), minutes=int(m.group(4))))
            else:
                tz = UTC
            return datetime.fromtimestamp(ms / 1000, tz=tz)
    return value


TPDateTime = Annotated[datetime, BeforeValidator(parse_tp_date)]

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def format_tp_date(value: datetime) -> str:
    """Encode a timezone-aware datetime as TP's ``/Date(ms±HHMM)/`` wire format.

    The inverse of :func:`parse_tp_date`. The offset written is the one the
    datetime carries, so the caller decides which offset TP records.

    Args:
        value: Timezone-aware datetime to encode.

    Returns:
        The TP wire representation, e.g. ``/Date(1718366400000+0200)/``.

    Raises:
        ValueError: ``value`` is naive, so no offset can be written.
        ValueError: ``value``'s offset is not a whole number of minutes, so
            it cannot be represented in TP's ``±HHMM`` wire format.
    """
    offset = value.utcoffset()
    if offset is None:
        raise ValueError("format_tp_date requires a timezone-aware datetime")
    if offset.total_seconds() % 60 != 0:
        raise ValueError(f"format_tp_date requires a whole-minute UTC offset, got {offset}")
    # Floor-divide two timedeltas rather than scaling ``timestamp()``: that
    # returns a float, and int() truncates toward zero, which is wrong for
    # pre-epoch instants.
    milliseconds = (value - _EPOCH) // timedelta(milliseconds=1)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"/Date({milliseconds}{sign}{hours:02d}{minutes:02d})/"
