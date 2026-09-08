"""Tests for AttachmentsResource."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import ClientMode, ReadOnlyViolation, TargetProcessClient
from targetprocess.exceptions import ParseError
from targetprocess.models import Attachment
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.attachments import AttachmentsResource


@pytest.mark.asyncio
async def test_attachments_resource_entity_type():
    """Test AttachmentsResource has correct entity_type."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = AttachmentsResource(mock_client, mock_request_handler)

    assert resource.entity_type == "Attachment"
    assert resource.model_class == Attachment


@pytest.mark.asyncio
async def test_attachments_inherits_crud():
    """Test AttachmentsResource inherits CRUD operations."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)

    resource = AttachmentsResource(mock_client, mock_request_handler)

    # Verify it has all CRUD methods from BaseResource
    assert hasattr(resource, "get")
    assert hasattr(resource, "list")
    assert hasattr(resource, "create")
    assert hasattr(resource, "update")
    assert hasattr(resource, "delete")


@pytest.mark.asyncio
async def test_attachments_download_fetches_uri_bytes():
    """Test download() delegates to the handler with the documented path."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.download_file.return_value = b"file-bytes"

    resource = AttachmentsResource(mock_client, mock_request_handler)

    result = await resource.download(1234)

    assert result == b"file-bytes"
    mock_request_handler.download_file.assert_called_once_with("/Attachment.aspx?AttachmentID=1234")


# The shape ``/UploadFile.ashx`` is recorded as answering with, reduced to the
# fields these tests read. Invented values throughout - the real recording
# lives in ``tests/integration/cassettes/test_live_readwrite_surfaces/``.
_UPLOAD_ENVELOPE = json.dumps(
    {
        "items": [
            {
                "resourceType": "Attachment",
                "id": 4321,
                "name": "sample.png",
                "uniqueFileName": "sample_0f1e2d3c.png",
                "date": "2026-09-05T07:06:20+02:00",
                "persistedMimeType": "image/png",
                "persistedSize": 9,
                "isEmpty": False,
                "uri": "https://example.tpondemand.com/Attachment.aspx?AttachmentID=4321",
                "mimeType": "image/png",
                "size": 9,
                "owner": {"resourceType": "GeneralUser", "id": 1, "fullName": "Alex Example"},
                "general": {"resourceType": "General", "id": 42, "name": "Sample story"},
            }
        ]
    }
)


@pytest.mark.asyncio
async def test_attachments_upload_sends_multipart_shape():
    """Test upload() checks writes, sends the wire shape, and types the response."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.upload_file.return_value = _UPLOAD_ENVELOPE

    resource = AttachmentsResource(mock_client, mock_request_handler)

    result = await resource.upload(42, "image.png", b"png-bytes", mime_type="image/png")

    assert result.id == 4321
    assert result.resource_type == "Attachment"
    assert result.size == 9
    assert result.persisted_size == 9
    assert result.is_empty is False
    assert result.general is not None
    assert result.general.id == 42
    assert result.owner is not None
    assert result.owner.full_name == "Alex Example"
    mock_client._check_write_permission.assert_called_once()
    mock_request_handler.upload_file.assert_called_once_with(
        "/UploadFile.ashx",
        data={"generalid": "42"},
        files={"file": ("image.png", b"png-bytes", "image/png")},
    )


@pytest.mark.asyncio
async def test_attachments_upload_without_mime_type_omits_it():
    """Test upload() sends a two-tuple file part when no MIME type is given."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.upload_file.return_value = _UPLOAD_ENVELOPE

    resource = AttachmentsResource(mock_client, mock_request_handler)

    await resource.upload(42, "notes.txt", b"text")

    mock_request_handler.upload_file.assert_called_once_with(
        "/UploadFile.ashx",
        data={"generalid": "42"},
        files={"file": ("notes.txt", b"text")},
    )


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("<html>login page</html>", "an auth redirect served as a page rather than a 3xx"),
        ("", "an empty body"),
        ('{"items": []}', "no record created"),
        ('{"items": [{"id": 1}, {"id": 2}]}', "more records than the one file sent"),
        ('{"Items": [{"id": 1}]}', "the entity API's PascalCase envelope, not this endpoint's"),
        ('["not-an-envelope"]', "a bare array"),
        ('{"items": [null]}', "a null where the record should be"),
        ('{"items": ["a-string"]}', "a string where the record should be"),
        ('{"items": [{"id": 1}]}', "a record that does not say it is an Attachment"),
        (
            '{"items": [{"id": 1, "resourceType": "UserStory"}]}',
            "a record of some other type entirely",
        ),
        ('{"items": [{"resourceType": "Attachment"}]}', "no id, the one field required"),
        (
            '{"items": [{"resourceType": "Attachment", "id": "not-an-int"}]}',
            "an id that is not a number",
        ),
    ],
)
def test_attachments_upload_response_that_cannot_be_parsed_raises(body: str, reason: str):
    """A body that is not the recorded envelope raises rather than returning half a result.

    The endpoint is undocumented, so each of these is a plausible thing a
    real instance might answer with. Returning something empty-but-valid for
    any of them would tell a caller the upload succeeded when nothing here
    knows that it did.

    ``ParseError`` specifically, not merely "raises": the last two fail
    inside pydantic, and a caller guarding an upload with
    ``except TargetProcessError`` catches a model-validation failure only
    because it is wrapped.

    The two ``resourceType`` cases are the ones a permissive model cannot
    catch on its own - every field but ``id`` is optional, so a bare record
    hydrates cleanly and would be returned as a created attachment.
    """
    with pytest.raises(ParseError):
        AttachmentsResource._parse_upload_response(body)


@pytest.mark.asyncio
async def test_attachments_writes_blocked_in_readonly_mode():
    """Test the full write path raises ReadOnlyViolation on a READONLY client."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )

    with pytest.raises(ReadOnlyViolation):
        await client.attachments.upload(42, "image.png", b"png-bytes")
    with pytest.raises(ReadOnlyViolation):
        await client.attachments.update(123, Description="y")
    with pytest.raises(ReadOnlyViolation):
        await client.attachments.delete(123)


@pytest.mark.asyncio
async def test_attachments_download_allowed_in_readonly_mode():
    """Test download() is a read - no write check, works on a READONLY client."""
    client = TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    )
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.download_file.return_value = b"ok"

    resource = AttachmentsResource(client, mock_request_handler)

    assert await resource.download(7) == b"ok"
