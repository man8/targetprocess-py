"""Tests for ProcessesResource (resolve() is covered in test_lookup_resolvers.py)."""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import RequestHandler, TargetProcessClient
from targetprocess.models import Process
from targetprocess.resources.processes import ProcessesResource


def test_processes_resource_entity_type():
    resource = ProcessesResource(Mock(spec=TargetProcessClient), AsyncMock(spec=RequestHandler))
    assert resource.entity_type == "Process"
    assert resource.model_class == Process
    # /meta: CanCreate, CanUpdate and CanDelete all true.
    assert all(ProcessesResource.server_permits(op) for op in ("create", "update", "delete"))


@pytest.mark.asyncio
async def test_processes_get_parses_process():
    """get() delegates to the handler and parses the process."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.get.return_value = {
        "Id": 2,
        "ResourceType": "Process",
        "Name": "Scrum",
        "Description": "Sample process description",
        "IsDefault": False,
    }

    resource = ProcessesResource(mock_client, mock_request_handler)

    result = await resource.get(2, include=["Name", "Description"])

    assert isinstance(result, Process)
    assert result.name == "Scrum"
    assert result.description == "Sample process description"
    mock_request_handler.get.assert_awaited_once()
    assert mock_request_handler.get.call_args.args == ("Process", 2)
    assert mock_request_handler.get.call_args.kwargs["include"] == ["Name", "Description"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["CustomFields", "customfields", "CustomFields[Id,Name]"])
async def test_processes_refuse_hydrating_custom_fields(field: str):
    """include= naming CustomFields is refused before any request, on get() and list().

    On a Process that key is the definitions collection (an Items envelope),
    which Entity.custom_fields cannot hold - so refusing up front replaces a
    ParseError after the round-trip. Any casing and the nested form count.
    """
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    resource = ProcessesResource(mock_client, mock_request_handler)

    with pytest.raises(ValueError, match="client.custom_fields") as excinfo:
        await resource.get(2, include=[field])
    assert f"include={field!r} is not supported on Process" in str(excinfo.value)
    with pytest.raises(ValueError, match="client.custom_fields"):
        async for _ in resource.list(include=["Name", field]):
            pass

    mock_request_handler.get.assert_not_called()
    mock_request_handler.list.assert_not_called()


@pytest.mark.asyncio
async def test_processes_still_hydrate_every_other_field():
    """The refusal is specific: an include naming only /meta fields goes through."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.get.return_value = {"Id": 2, "ResourceType": "Process", "Name": "Scrum"}
    resource = ProcessesResource(mock_client, mock_request_handler)

    result = await resource.get(2, include=["Name", "Description", "IsDefault"])

    assert result.name == "Scrum"
    assert mock_request_handler.get.call_args.kwargs["include"] == [
        "Name",
        "Description",
        "IsDefault",
    ]
