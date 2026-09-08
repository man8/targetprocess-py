"""Workflow resource manager."""

from targetprocess.models import Workflow
from targetprocess.resources.base import BaseResource


class WorkflowsResource(BaseResource[Workflow]):
    """Resource manager for Workflow entities.

    A workflow is scoped to one process and one entity type, and its columns
    are the EntityState records (``client.entity_states``, filtered by
    ``Workflow.Id``). Names repeat across processes ("Project workflow" in
    each), so there is no instance-wide ``resolve``: narrow by process and
    entity type instead. The collection is writable on the server, so the
    full CRUD surface applies.

    Example:
        client = TargetProcessClient(...)
        async for workflow in client.workflows.list(
            where="(Process.Id eq 2) and (EntityType.Name eq 'Bug')",
            include=["Name", "Process", "EntityType", "ParentWorkflow"],
        ):
            print(workflow.name, workflow.parent_workflow)
    """

    entity_type = "Workflow"
    model_class = Workflow
