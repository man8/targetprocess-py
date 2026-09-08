"""Relation resource manager."""

from targetprocess.models import Relation
from targetprocess.resources.base import BaseResource


class RelationsResource(BaseResource[Relation]):
    """Resource manager for Relation entities.

    A Relation links a ``Master`` entity to a ``Slave`` entity, typed by a
    ``RelationType`` (Dependency, Blocker, Relation, Duplicate, ...). The
    direction carries meaning: the Master is the source of the dependency -
    in a Blocker relation the Master is the blocking item and the Slave the
    blocked one. Creating one takes the three references; removing one
    deletes the Relation record itself.

    RelationType Ids are instance-specific, so resolve them by name via
    ``client.relation_types`` rather than hardcoding.

    Example:
        client = TargetProcessClient(...)
        async for r in client.relations.list(
            where="Slave.Id eq 123",
            include=["Master", "Slave", "RelationType"],
        ):
            print(r.master, r.relation_type)
        blocker = await client.relation_types.resolve("Blocker")
        await client.relations.create(
            Master={"Id": 456}, Slave={"Id": 123}, RelationType={"Id": blocker.id}
        )
    """

    entity_type = "Relation"
    model_class = Relation
