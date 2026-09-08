"""TestCase resource manager."""

from targetprocess.models import TestCase
from targetprocess.resources.base import BaseResource


class TestCasesResource(BaseResource[TestCase]):
    """Resource manager for TestCase entities.

    Provides type-safe CRUD operations for test cases.

    Example:
        client = TargetProcessClient(...)
        test_case = await client.test_cases.get(123)
        async for test_case in client.test_cases.list(limit=10):
            print(test_case.name)
    """

    entity_type = "TestCase"
    model_class = TestCase
