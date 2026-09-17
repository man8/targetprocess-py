"""EntityState resource manager."""

from targetprocess.models import EntityState
from targetprocess.resources.base import BaseResource, _resolve_by_name

# The fields a workflow-scoped lookup asks for. Named explicitly rather than
# left to the default projection, which is not documented to carry the
# ``Workflow`` reference, and which the state-transition helpers read along
# with the entry gates (``IsCommentRequired``, ``Role``).
_STATE_INCLUDE = [
    "Id",
    "Name",
    "IsFinal",
    "IsInitial",
    "IsCommentRequired",
    "NumericPriority",
    "Workflow",
    "Role",
]


class EntityStatesResource(BaseResource[EntityState]):
    """Resource manager for EntityState entities.

    An entity state is one column of a workflow, and a workflow is scoped to
    one process and one entity type. State names are resolved within a
    workflow rather than instance-wide: the same name ("Done", "In Progress")
    exists once per workflow, and workflows repeat per process, so a bare name
    is ambiguous across the instance but identifies one state inside one
    workflow. The item a state belongs to names its workflow through the
    state's own ``Workflow`` reference.

    Example:
        client = TargetProcessClient(...)
        story = await client.user_stories.get(123, include=["EntityState"])
        current = await client.entity_states.get(story.entity_state.id, include=["Workflow"])
        done = await client.entity_states.resolve("Done", workflow_id=current.workflow.id)
        for state in await client.entity_states.final_states(current.workflow.id):
            print(state.id, state.name)
    """

    entity_type = "EntityState"
    model_class = EntityState

    async def for_workflow(self, workflow_id: int) -> list[EntityState]:
        """Return every state of one workflow, in API order.

        Each state carries ``Workflow``, ``IsFinal``, ``IsInitial``,
        ``IsCommentRequired``, ``NumericPriority`` and ``Role`` alongside its
        ``Id`` and ``Name``.

        Args:
            workflow_id: The workflow's Id

        Returns:
            The workflow's states, in API order.

        Raises:
            ValueError: ``workflow_id`` is not an integer (it is interpolated
                into the ``where=`` filter, so nothing else is sent).
            RequestValidationError: TP rejected the resulting filter.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        where = f"Workflow.Id eq {int(workflow_id)}"
        return [state async for state in self.list(where=where, include=_STATE_INCLUDE)]

    async def resolve(self, name: str, *, workflow_id: int) -> EntityState:
        """Resolve a state name to the one state of that name in a workflow.

        Matching is case-insensitive. A name matching zero or several states
        raises rather than picking a candidate, so a guessed state Id never
        reaches a write.

        This issues one HTTP request per call; callers resolving several
        states of one workflow should call ``for_workflow()`` once and match
        locally instead of calling ``resolve()`` in a loop.

        Args:
            name: State display name (e.g. ``"Done"``)
            workflow_id: The workflow the state belongs to

        Returns:
            The single matching EntityState.

        Raises:
            NotFoundError: No state of that name exists in the workflow (the
                message lists the names that do).
            AmbiguousMatchError: More than one state of that name matched.
            ValueError: ``workflow_id`` is not an integer.
            RequestValidationError: TP rejected the resulting filter.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        candidates = await self.for_workflow(workflow_id)
        return _resolve_by_name(candidates, name, what=f"workflow {int(workflow_id)} state")

    async def final_states(self, workflow_id: int) -> list[EntityState]:
        """Return the final states of one workflow, in API order.

        A workflow can hold several final states - a completed column and a
        rejected or cancelled one - so this returns every state whose
        ``IsFinal`` is true, and an empty list when the workflow has none.

        Args:
            workflow_id: The workflow's Id

        Returns:
            The workflow's final states, in API order.

        Raises:
            ValueError: ``workflow_id`` is not an integer.
            RequestValidationError: TP rejected the resulting filter.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            ParseError: Response failed model validation
            APIError: Other API errors
        """
        return [state for state in await self.for_workflow(workflow_id) if state.is_final is True]
