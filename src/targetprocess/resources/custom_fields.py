"""CustomField resource manager."""

from targetprocess.models import CustomField
from targetprocess.resources.base import BaseResource


class CustomFieldsResource(BaseResource[CustomField]):
    """Resource manager for CustomField definitions.

    A CustomField record is the *definition* of a field configured on a
    process for one entity type - its type, constraints and metadata - not a
    value held by an entity (those arrive in each entity's ``custom_fields``).
    Definitions are scoped by process and entity type, so a name repeats
    across processes: filter rather than resolve, e.g.
    ``where="(Process.Id eq 2) and (EntityType.Name eq 'UserStory')"``. The
    collection is writable on the server, so the full CRUD surface applies.

    Example:
        client = TargetProcessClient(...)
        async for field in client.custom_fields.list(
            where="EntityType.Name eq 'Bug'", include=["Name", "FieldType", "Required"]
        ):
            print(field.name, field.field_type, field.required)
    """

    entity_type = "CustomField"
    model_class = CustomField
