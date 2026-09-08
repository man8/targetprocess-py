"""Tests for Attachment model."""

from datetime import datetime

from targetprocess.models import Attachment


def test_attachment_full_parsing() -> None:
    data = {
        "Id": 1,
        "Name": "screenshot.png",
        "ResourceType": "Attachment",
        "UniqueFileName": "abc123.png",
        "Description": "a screenshot",
        "Date": "/Date(1423474908000+0100)/",
        "Owner": {"ResourceType": "GeneralUser", "Id": 17, "FullName": "Sam Roe"},
        "General": {"Id": 417, "Name": "Story C"},
        "Message": None,
        "Uri": "/Attachment.aspx?AttachmentID=1",
        "MimeType": "image/png",
        "Size": 54321,
        "ThumbnailUri": "/AttachmentThumbnail.aspx?AttachmentID=1",
    }
    a = Attachment.model_validate(data)
    assert a.id == 1
    assert a.name == "screenshot.png"
    assert a.unique_file_name == "abc123.png"
    assert a.description == "a screenshot"
    assert isinstance(a.date, datetime)
    assert a.date.timestamp() == 1423474908.0
    assert a.owner is not None and a.owner.id == 17
    assert a.general is not None and a.general.name == "Story C"
    assert a.message is None
    assert a.uri == "/Attachment.aspx?AttachmentID=1"
    assert a.mime_type == "image/png"
    assert a.size == 54321
    assert a.thumbnail_uri == "/AttachmentThumbnail.aspx?AttachmentID=1"


def test_attachment_file_fields_are_declared() -> None:
    # Uri/MimeType/Size/ThumbnailUri are declared fields, not extra="allow"
    # passthroughs - the location of an attachment's own bytes is part of the
    # typed surface.
    a = Attachment.model_validate(
        {
            "Id": 2,
            "Name": "f.pdf",
            "ResourceType": "Attachment",
            "Uri": "/Attachment.aspx?AttachmentID=2",
            "MimeType": "application/pdf",
            "Size": 10,
            "ThumbnailUri": None,
        }
    )
    extras = a.model_extra or {}
    for key in ("Uri", "MimeType", "Size", "ThumbnailUri"):
        assert key not in extras


def test_attachment_minimal_parsing() -> None:
    a = Attachment.model_validate({"Id": 3, "Name": "f", "ResourceType": "Attachment"})
    assert a.id == 3
    assert a.unique_file_name is None
    assert a.owner is None
    assert a.uri is None
    assert a.mime_type is None
    assert a.size is None
    assert a.thumbnail_uri is None
