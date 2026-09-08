"""Tests for the UploadedAttachment and UploadedFileRef models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from targetprocess.models import UploadedAttachment, UploadedFileRef

# The shape ``/UploadFile.ashx`` is recorded as answering with. Invented
# values - the real recording is in
# ``tests/integration/cassettes/test_live_readwrite_surfaces/``.
_BODY = {
    "resourceType": "Attachment",
    "id": 4321,
    "name": "sample.png",
    "uniqueFileName": "sample_0f1e2d3c.png",
    "description": "sample.png",
    "date": "2026-09-05T07:06:20+02:00",
    "persistedMimeType": "image/png",
    "persistedSize": 9,
    "isEmpty": False,
    "uri": "https://example.tpondemand.com/Attachment.aspx?AttachmentID=4321",
    "thumbnailUri": "https://example.tpondemand.com/AttachmentThumbnail.aspx?AttachmentID=4321",
    "mimeType": "image/png",
    "size": 9,
    "owner": {
        "resourceType": "GeneralUser",
        "id": 1,
        "firstName": "Alex",
        "lastName": "Example",
        "login": "alex",
        "fullName": "Alex Example",
    },
    "general": {"resourceType": "General", "id": 42, "name": "Sample story"},
    "message": None,
    "assignable": {"resourceType": "Assignable", "id": 42, "name": "Sample story"},
}


def test_uploaded_attachment_full_parsing() -> None:
    """Every field the endpoint sends hydrates, under its camelCase alias."""
    uploaded = UploadedAttachment.model_validate(_BODY)

    assert uploaded.id == 4321
    assert uploaded.resource_type == "Attachment"
    assert uploaded.name == "sample.png"
    assert uploaded.unique_file_name == "sample_0f1e2d3c.png"
    assert uploaded.description == "sample.png"
    assert uploaded.persisted_mime_type == "image/png"
    assert uploaded.persisted_size == 9
    assert uploaded.is_empty is False
    assert uploaded.mime_type == "image/png"
    assert uploaded.size == 9
    assert uploaded.uri is not None
    assert uploaded.thumbnail_uri is not None
    assert uploaded.message is None


def test_uploaded_attachment_date_is_iso_not_tp_wire_format() -> None:
    """This endpoint sends ISO-8601 where the entity API sends ``/Date(ms±HHMM)/``.

    ``TPDateTime``'s validator passes a non-matching string through to
    pydantic, which is what makes one annotation serve both, so the divergence
    is worth a test rather than a note: it is the only place in the library
    where that pass-through is the *normal* path.
    """
    uploaded = UploadedAttachment.model_validate(_BODY)

    assert isinstance(uploaded.date, datetime)
    assert uploaded.date.utcoffset() is not None
    assert uploaded.date.year == 2026
    assert uploaded.date.hour == 7


def test_uploaded_attachment_references_hydrate_both_shapes() -> None:
    """One reference model covers a user reference and an entity reference.

    The endpoint inlines the uploader's name fields where the entity API
    would send a bare ``{Id, Name}``, so the two shapes have to coexist.
    """
    uploaded = UploadedAttachment.model_validate(_BODY)

    assert uploaded.owner is not None
    assert uploaded.owner.id == 1
    assert uploaded.owner.login == "alex"
    assert uploaded.owner.full_name == "Alex Example"
    assert uploaded.owner.name is None
    assert uploaded.general is not None
    assert uploaded.general.id == 42
    assert uploaded.general.name == "Sample story"
    assert uploaded.general.login is None


def test_uploaded_attachment_keeps_undeclared_fields() -> None:
    """An undocumented endpoint may add a field; it is preserved, not dropped."""
    uploaded = UploadedAttachment.model_validate({**_BODY, "somethingNew": "kept"})

    assert (uploaded.model_extra or {}).get("somethingNew") == "kept"


def test_uploaded_attachment_requires_an_id() -> None:
    """``id`` is the one field a created record cannot be useful without."""
    without_id = {key: value for key, value in _BODY.items() if key != "id"}

    with pytest.raises(ValidationError):
        UploadedAttachment.model_validate(without_id)


@pytest.mark.parametrize("field", ["size", "persistedSize"])
def test_uploaded_attachment_rejects_a_negative_size(field: str) -> None:
    """A byte count below zero is not a shape this endpoint can legitimately send."""
    with pytest.raises(ValidationError):
        UploadedAttachment.model_validate({**_BODY, field: -1})


def test_uploaded_file_ref_tolerates_a_bare_reference() -> None:
    """Every field is optional: the endpoint sends different subsets per role."""
    ref = UploadedFileRef.model_validate({"resourceType": "General", "id": 7})

    assert ref.id == 7
    assert ref.resource_type == "General"
    assert ref.name is None
    assert ref.first_name is None
