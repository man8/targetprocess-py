"""Relation resource manager."""

from targetprocess_py.models import Relation
from targetprocess_py.resources.base import BaseResource


class RelationsResource(BaseResource[Relation]):
    """Resource manager for Relation entities.

    A Relation links an ``Inbound`` (source) entity to an ``Outbound``
    (target) entity, typed by a ``RelationType`` (Dependency, Blocker,
    Relation, Duplicate, ...). The direction carries meaning: the source is
    the origin of the dependency - in a Blocker relation the Inbound is the
    blocking item and the Outbound the blocked one. ``Master``/``Slave`` are
    the deprecated names for the same pair. Creating one takes the three
    references; removing one deletes the Relation record itself.

    RelationType Ids are instance-specific, so resolve them by name via
    ``client.relation_types`` rather than hardcoding.

    Example:
        client = TargetProcessClient(...)
        # What blocks item 123?
        async for r in client.relations.list(
            where="Outbound.Id eq 123",
            include=["Inbound", "Outbound", "RelationType"],
        ):
            print(r.inbound, r.relation_type)
        blocker = await client.relation_types.resolve("Blocker")
        await client.relations.create(
            Inbound={"Id": 456}, Outbound={"Id": 123}, RelationType={"Id": blocker.id}
        )
    """

    entity_type = "Relation"
    model_class = Relation
