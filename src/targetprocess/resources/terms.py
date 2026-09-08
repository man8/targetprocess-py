"""Term resource manager."""

from targetprocess.models import Term
from targetprocess.resources.base import BaseResource


class TermsResource(BaseResource[Term]):
    """Resource manager for Term entities.

    A term is one process's display word for an entity type (see
    :class:`targetprocess.models.Term`). TP declares the collection itself
    read-only, and the resource enforces that client-side: ``create``,
    ``update`` and ``delete`` (and the bulk pair) raise ``ReadOnlyViolation``
    in every client mode - READWRITE included - before any request is sent.
    A Term carries no ``Name``, so there is no ``resolve``; filter by process
    and entity type.

    Example:
        client = TargetProcessClient(...)
        async for term in client.terms.list(
            where="Process.Id eq 2", include=["WordKey", "Value", "EntityType"]
        ):
            print(term.word_key, "->", term.value)
    """

    entity_type = "Term"
    model_class = Term
    server_read_only = True
