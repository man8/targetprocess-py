"""The fields TargetProcess derives from another collection, and the write refusal.

A derived field is one TP computes from records in another collection rather
than storing what a write sends. A direct write to one is answered with a
success status either way, so the response cannot say which of two things
happened: TP stored the value because the source collection was empty, or TP
recomputed the field from that collection and the write changed nothing. The
outcome therefore depends on the entity's other records rather than on the
request, and a caller cannot tell the cases apart without reading the source
collection first.

That is why the refusal is *before* the request, alongside ``check_include``
and ``check_where``, rather than the verification that follows a write: a
re-read distinguishes "stored because nothing overrode it" from "recomputed
back to the same number" only by luck, and the route named in each message
writes the source record instead, which is deterministic whatever the
collection holds.

``ValueError`` is the exception, as for every other guard that refuses an
unsupported argument before sending (``check_include``, ``check_where``, the
bulk ``Id`` shape checks). ``ReadOnlyViolation`` is deliberately not reused: it
answers "this client, or this collection, may not write at all", and a caller
distinguishing that from "this one field is derived" should not have to read
the message to do it.

A caller who means the direct write - typically because the source collection
is known to be empty, which is how this library's own recorded write fixtures
use it - passes ``allow_derived=True`` and takes the outcome as TP gives it.

The declared set is what has been established, not every candidate. An
Assignable carries other numbers TP computes (``Progress`` from effort,
``TimeSpent`` and ``TimeRemain`` from Time entries, ``LeadTime`` and
``CycleTime`` from dates) and none is declared here: each would need its own
route named in its own message, and the same live evidence
``ASSIGNABLE_IGNORED_FILTER_PATHS`` is extended on.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def _role_effort_route(field: str) -> str:
    """Return the reason for one of the roll-ups an Assignable carries over its RoleEfforts.

    Args:
        field: The wire field name, named in the message so it reads for the
            field the caller actually wrote.

    Returns:
        Why TP derives the field, and the RoleEffort route that sets it.
    """
    return (
        f"TargetProcess derives {field} from the entity's RoleEfforts, so a direct write is "
        "stored or recomputed away according to whether that collection is empty, and the "
        "success status says nothing about which; set the role's own row instead - find it "
        'with client.role_efforts.list(where="Assignable.Id eq <id>", include=["Role"]) and '
        f"write {field} there with client.role_efforts.update, or create the row with "
        "client.role_efforts.create for a role that has none. Pass allow_derived=True to "
        "send the write anyway."
    )


# Wire field name -> why TP derives it, and the route that sets the value. The
# one place the assignable set is declared: ``AssignableResource`` carries it as
# its ``derived_fields``, and the generic entities path mirrors it for those
# managers' collections and for the Assignable-derived collections that have no
# typed manager. Effort and its two companions are one roll-up in three
# projections - the total, the part done and the part left - so they share a
# route and are guarded together.
ASSIGNABLE_DERIVED_FIELDS: dict[str, str] = {
    field: _role_effort_route(field) for field in ("Effort", "EffortCompleted", "EffortToDo")
}


def check_derived_fields(
    fields: Iterable[str],
    derived: Mapping[str, str],
    *,
    resource: str,
    prefix: str = "",
) -> None:
    """Refuse a write naming a field TP derives from another collection.

    Matching is case-insensitive and ignores surrounding whitespace, as the
    verification comparison's key matching does. A collection with nothing
    declared accepts every field, as before.

    Args:
        fields: The wire field names the write would send
        derived: Wire field name -> why TP derives it, and the route that sets
            the value
        resource: The entity type name to report - the class's own for a typed
            resource, the caller's spelling on the generic path
        prefix: Text to open the message with, naming the batch item on a bulk
            path (e.g. ``"update_many item 0: "``)

    Raises:
        ValueError: A field is one TP derives for this collection; the message
            names the field, the collection, why, and the route to use instead.
    """
    if not derived:
        return
    reasons = {name.casefold(): reason for name, reason in derived.items()}
    for field in fields:
        reason = reasons.get(field.strip().casefold())
        if reason is not None:
            raise ValueError(f"{prefix}{field} is not writable on {resource}: {reason}")


def check_derived_items(
    items: Sequence[Mapping[str, Any]],
    derived: Mapping[str, str],
    *,
    resource: str,
    operation: str,
) -> None:
    """Apply :func:`check_derived_fields` to every item of a bulk batch.

    Args:
        items: The batch, each item's keys the wire fields it would send
        derived: Wire field name -> why TP derives it, and the route that sets
            the value
        resource: The entity type name to report
        operation: The calling method, so the message names the item the way
            the batch's other refusals do (``"create_many"`` /
            ``"update_many"``)

    Raises:
        ValueError: An item names a field TP derives for this collection; the
            message names the item's zero-based position.
    """
    for position, item in enumerate(items):
        check_derived_fields(
            item, derived, resource=resource, prefix=f"{operation} item {position}: "
        )
