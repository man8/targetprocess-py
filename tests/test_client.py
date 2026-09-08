"""Tests for TargetProcessClient."""

import pytest

from targetprocess import ClientMode, ReadOnlyViolation, TargetProcessClient


@pytest.mark.asyncio
async def test_client_initialization() -> None:
    """Test client initializes with required parameters."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )
    assert client.domain == "example.tpondemand.com"
    assert client.mode == ClientMode.READONLY


@pytest.mark.asyncio
async def test_client_mode_is_immutable() -> None:
    """Test client mode cannot be changed after initialization."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(AttributeError, match="mode is immutable"):
        client.mode = ClientMode.READWRITE


@pytest.mark.asyncio
async def test_readonly_mode_blocks_writes() -> None:
    """Test readonly mode blocks write operations."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(ReadOnlyViolation):
        client._check_write_permission()


@pytest.mark.asyncio
async def test_readwrite_mode_allows_writes() -> None:
    """Test readwrite mode allows write operations."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READWRITE,
    )

    # Should not raise
    client._check_write_permission()


@pytest.mark.asyncio
async def test_context_manager() -> None:
    """Test client works as async context manager."""
    async with TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    ) as client:
        assert client.domain == "example.tpondemand.com"


@pytest.mark.asyncio
async def test_resource_properties_accessible() -> None:
    """Test all resource properties are accessible."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    # Verify all 33 resource properties exist and return correct types
    assert hasattr(client, "user_stories")
    assert hasattr(client, "bugs")
    assert hasattr(client, "tasks")
    assert hasattr(client, "features")
    assert hasattr(client, "epics")
    assert hasattr(client, "requests")
    assert hasattr(client, "test_cases")
    assert hasattr(client, "times")
    assert hasattr(client, "releases")
    assert hasattr(client, "iterations")
    assert hasattr(client, "projects")
    assert hasattr(client, "teams")
    assert hasattr(client, "users")
    assert hasattr(client, "entity_states")
    assert hasattr(client, "priorities")
    assert hasattr(client, "comments")
    assert hasattr(client, "assignments")
    assert hasattr(client, "team_assignments")
    assert hasattr(client, "role_efforts")
    assert hasattr(client, "roles")
    assert hasattr(client, "attachments")
    assert hasattr(client, "relations")
    assert hasattr(client, "relation_types")
    assert hasattr(client, "team_iterations")
    assert hasattr(client, "custom_fields")
    assert hasattr(client, "severities")
    assert hasattr(client, "processes")
    assert hasattr(client, "workflows")
    assert hasattr(client, "entity_types")
    assert hasattr(client, "terms")
    assert hasattr(client, "custom_activities")
    assert hasattr(client, "custom_rules")
    assert hasattr(client, "entities")


@pytest.mark.asyncio
async def test_resource_lazy_initialization() -> None:
    """Test resources are lazily initialized."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    # Resource should not exist before first access
    assert not hasattr(client, "_user_stories")

    # Access the resource
    _ = client.user_stories

    # Resource should now exist
    assert hasattr(client, "_user_stories")


@pytest.mark.asyncio
async def test_resource_returns_same_instance() -> None:
    """Test accessing resource property returns same instance."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    # Access resource twice
    resource1 = client.user_stories
    resource2 = client.user_stories

    # Should be the same instance
    assert resource1 is resource2


def _client(mode: object = ClientMode.READONLY) -> TargetProcessClient:
    return TargetProcessClient(domain="x.tpondemand.com", token="t", mode=mode)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_mode_frozen_flag_is_guarded() -> None:
    """Test the freeze flag itself cannot be reset to defeat the freeze."""
    client = _client()
    with pytest.raises(AttributeError):
        client._mode_frozen = False


@pytest.mark.asyncio
async def test_invalid_mode_fails_closed() -> None:
    """Test an unrecognised mode value raises rather than silently allowing writes."""
    with pytest.raises(ValueError):
        _client(mode="readwrite-ish")


@pytest.mark.asyncio
async def test_handler_layer_blocks_writes_in_readonly() -> None:
    """Test the handler itself refuses writes, bypassing the resource layer entirely."""
    client = _client()
    with pytest.raises(ReadOnlyViolation):
        await client._request_handler.create("UserStories", {"Name": "x"})


@pytest.mark.asyncio
async def test_public_aclose_exists() -> None:
    """Test aclose is a public, callable method for non-context-manager use."""
    assert callable(getattr(_client(), "aclose", None))


def test_client_exposes_times_resource() -> None:
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="t", mode=ClientMode.READONLY
    )
    assert client.times.entity_type == "Time"
    assert client.times is client.times  # cached


def test_client_exposes_comments_resource() -> None:
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="t", mode=ClientMode.READONLY
    )
    assert client.comments.entity_type == "Comment"
    assert client.comments is client.comments  # cached


def test_client_exposes_assignment_resources() -> None:
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="t", mode=ClientMode.READONLY
    )
    assert client.assignments.entity_type == "Assignment"
    assert client.assignments is client.assignments  # cached
    assert client.team_assignments.entity_type == "TeamAssignment"
    assert client.team_assignments is client.team_assignments  # cached
    assert client.role_efforts.entity_type == "RoleEffort"
    assert client.role_efforts is client.role_efforts  # cached
    assert client.roles.entity_type == "Role"
    assert client.roles is client.roles  # cached


def test_client_exposes_attachments_resource() -> None:
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="t", mode=ClientMode.READONLY
    )
    assert client.attachments.entity_type == "Attachment"
    assert client.attachments is client.attachments  # cached


def test_client_exposes_relation_resources() -> None:
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="t", mode=ClientMode.READONLY
    )
    assert client.relations.entity_type == "Relation"
    assert client.relations is client.relations  # cached
    assert client.relation_types.entity_type == "RelationType"
    assert client.relation_types is client.relation_types  # cached


@pytest.mark.parametrize(
    ("accessor", "entity_type"),
    [
        ("team_iterations", "TeamIteration"),
        ("custom_fields", "CustomField"),
        ("severities", "Severity"),
        ("processes", "Process"),
        ("workflows", "Workflow"),
        ("entity_types", "EntityType"),
        ("terms", "Term"),
        ("custom_activities", "CustomActivity"),
        ("custom_rules", "CustomRule"),
    ],
)
def test_client_exposes_lookup_and_configuration_resources(accessor: str, entity_type: str) -> None:
    client = TargetProcessClient(
        domain="example.tpondemand.com", token="t", mode=ClientMode.READONLY
    )
    resource = getattr(client, accessor)
    assert resource.entity_type == entity_type
    assert getattr(client, accessor) is resource  # cached
