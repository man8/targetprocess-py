"""Tests for TermsResource.

The server-read-only refusals are covered in test_server_capability.py; this
file pins the class contract and the read path.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import ClientMode, RequestHandler, TargetProcessClient
from targetprocess.models import Term
from targetprocess.resources.terms import TermsResource
from tests._support.request_handler import scripted_list


def test_terms_resource_entity_type():
    resource = TermsResource(Mock(spec=TargetProcessClient), AsyncMock(spec=RequestHandler))
    assert resource.entity_type == "Term"
    assert resource.model_class == Term
    # /meta: CanCreate, CanUpdate and CanDelete all false.
    assert TermsResource.server_read_only is True
    assert not any(TermsResource.server_permits(op) for op in ("create", "update", "delete"))
    # A Term has no Name, so there is nothing to resolve by.
    assert not hasattr(resource, "resolve")


@pytest.mark.asyncio
async def test_terms_list_parses_nameless_records():
    """list() yields Terms keyed by WordKey/Value, with no Name attribute at all."""
    _list, seen = scripted_list(
        [
            {
                "Id": 11,
                "ResourceType": "Term",
                "WordKey": "UserStory",
                "Value": "Ticket",
                "Process": {"ResourceType": "Process", "Id": 2, "Name": "Scrum"},
                "EntityType": {"ResourceType": "EntityType", "Id": 4, "Name": "UserStory"},
            }
        ]
    )
    client = Mock(spec=TargetProcessClient)
    client.mode = ClientMode.READONLY
    handler = Mock(spec=RequestHandler)
    handler.list = _list
    resource = TermsResource(client, handler)

    (term,) = [t async for t in resource.list(where="Process.Id eq 2")]

    assert seen["entity_type"] == "Term" and seen["where"] == "Process.Id eq 2"
    assert isinstance(term, Term)
    assert term.word_key == "UserStory"
    assert term.value == "Ticket"
    assert term.entity_type is not None and term.entity_type.id == 4
    assert not hasattr(term, "name")
