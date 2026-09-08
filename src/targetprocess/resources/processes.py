"""Process resource manager."""

from targetprocess.models import Process
from targetprocess.resources.base import BaseResource, _resolve_by_name


class ProcessesResource(BaseResource[Process]):
    """Resource manager for Process entities.

    A process is the unit of configuration a Project follows, and its Id is
    the key that scopes workflows, custom-field definitions and terms - so
    resolving a process name is the first step of most configuration
    queries. The collection is writable on the server, so the full CRUD
    surface applies.

    One include is refused: on a Process, TP's ``CustomFields`` is the
    collection of custom-field *definitions* (an ``Items`` envelope), not
    the values array every model carries, so ``get``/``list`` raise
    ``ValueError`` on ``include=["CustomFields"]`` before any request rather
    than failing the parse afterwards. List the definitions through
    ``client.custom_fields`` filtered by ``Process.Id`` instead.

    Example:
        client = TargetProcessClient(...)
        scrum = await client.processes.resolve("Scrum")
        async for workflow in client.workflows.list(where=f"Process.Id eq {scrum.id}"):
            print(workflow.name)
    """

    entity_type = "Process"
    model_class = Process
    unhydratable_includes = {
        "CustomFields": "on a Process it is the collection of custom-field definitions "
        "(an Items envelope), not the values array Entity.custom_fields holds - list "
        "definitions via client.custom_fields filtered by Process.Id"
    }

    async def resolve(self, name: str) -> Process:
        """Resolve a process name to its single Process record.

        Matching is case-insensitive. A name matching zero or several records
        raises rather than picking a candidate, so an ambiguous resolution
        never reaches the API.

        This issues one HTTP request per call; callers resolving several
        processes should call ``list()`` once and match locally instead of
        calling ``resolve()`` in a loop.

        Args:
            name: Process display name (e.g. ``"Scrum"``)

        Returns:
            The single matching Process.

        Raises:
            NotFoundError: No process of that name exists (the message lists
                the names that do).
            AmbiguousMatchError: More than one process of that name matched.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        return _resolve_by_name([p async for p in self.list()], name, what="process")
