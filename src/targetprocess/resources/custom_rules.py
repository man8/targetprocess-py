"""CustomRule resource manager."""

from targetprocess.models import CustomRule
from targetprocess.resources.base import BaseResource


class CustomRulesResource(BaseResource[CustomRule]):
    """Resource manager for CustomRule entities.

    TP exposes business rules for inspection and toggling only: the
    collection's ``/meta`` declares it neither creatable nor deletable, and
    ``IsEnabled`` is the one settable field. The resource enforces that
    client-side - ``create``, ``create_many`` and ``delete`` raise
    ``ReadOnlyViolation`` in every client mode, READWRITE included, before
    any request is sent - while ``update`` and ``update_many`` go through
    under the ordinary READWRITE gate.

    Example:
        client = TargetProcessClient(...)
        async for rule in client.custom_rules.list(where="IsEnabled eq 'true'"):
            print(rule.id, rule.name)
        await client.custom_rules.update(9, IsEnabled=False)
    """

    entity_type = "CustomRule"
    model_class = CustomRule
    server_can_create = False
    server_can_delete = False
