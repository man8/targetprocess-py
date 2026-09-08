"""Entity type name validation, shared by every layer that interpolates one."""

import re

_ENTITY_TYPE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def require_entity_type(entity_type: str) -> None:
    """Refuse an entity type name that is not a plain TP identifier.

    An entity type name is interpolated straight into a request path (and,
    in ``priorities.for_entity_type``, into a ``where=`` filter). On the
    generic ``entities`` resource it is caller-supplied at runtime - often
    echoing a server-returned ``ResourceType`` - so anything beyond a bare
    identifier changes what the request does: ``"UserStories/57731"`` turns
    a create into an update of that entity, and a trailing slash or stray
    whitespace slips past a name-keyed guard. TP collection names are plain
    identifiers, so that is all that is accepted - the same stance as
    ``RequestHandler._require_instance_path``: enforced, not merely
    documented.

    Args:
        entity_type: The entity type name to check

    Raises:
        ValueError: ``entity_type`` is not letters, digits and underscores
            starting with a letter.
    """
    if not _ENTITY_TYPE_RE.fullmatch(entity_type):
        raise ValueError(
            "entity_type must be a TP entity type name (letters, digits, "
            f"underscore): {entity_type!r}"
        )
