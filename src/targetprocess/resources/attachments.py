"""Attachment resource manager."""

import json

import pydantic

from targetprocess.exceptions import ParseError
from targetprocess.models import Attachment, UploadedAttachment
from targetprocess.resources.base import BaseResource


class AttachmentsResource(BaseResource[Attachment]):
    """Resource manager for Attachment entities.

    Provides the usual typed CRUD surface over attachment *records*, plus the
    two file-transfer helpers TargetProcess keeps outside its JSON entity API:
    ``download`` fetches an attachment's bytes, and ``upload`` sends a new
    file via the vendor-documented multipart endpoint, returning the created
    record as :class:`~targetprocess.models.UploadedAttachment`. ``general``
    names the entity a file is attached to; ``uri`` on a fetched record is
    the instance-root download path ``download`` resolves - and is only
    populated when asked for by ``include=``, a plain ``get`` leaving it,
    ``mime_type`` and ``size`` unset.

    TargetProcess documents its file endpoints against Basic auth, and the
    vendor guide states that a REST API token cannot be used to download an
    attached file. That is not what a token-auth client actually meets: the
    write-path integration suite records both an upload and a download of the
    uploaded bytes succeeding under token auth. The redirect these helpers
    refuse is therefore a real failure to surface, not the expected outcome -
    a 3xx here means the file was not transferred.

    Example:
        client = TargetProcessClient(...)
        attachment = await client.attachments.get(1234)
        content = await client.attachments.download(1234)
    """

    entity_type = "Attachment"
    model_class = Attachment

    async def download(self, id: int) -> bytes:
        """Download an attachment's file content.

        Fetches the bytes from the instance-root download path
        (``/Attachment.aspx?AttachmentID=<id>`` - the same path a fetched
        record carries in ``uri``), which sits outside ``/api/v1``.

        Args:
            id: Attachment ID

        Returns:
            The file content

        Raises:
            APIError: The server redirected instead of serving the file
                (typically the login page, when the auth scheme is not
                accepted for downloads - see the class docstring), or
                another API error occurred.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NotFoundError: Attachment not found
            NetworkError: Transport-level failure
        """
        return await self._request_handler.download_file(f"/Attachment.aspx?AttachmentID={id}")

    async def upload(
        self,
        general_id: int,
        filename: str,
        content: bytes,
        *,
        mime_type: str | None = None,
    ) -> UploadedAttachment:
        """Upload a file as an attachment on an entity.

        Requires client mode to be READWRITE. Sends the vendor-documented
        wire shape - ``POST /UploadFile.ashx`` as ``multipart/form-data``
        with a ``generalid`` form field and the file as a ``file`` part.

        TargetProcess documents the request but not the response. What it
        answers with, recorded in the write-path integration suite, is a
        camelCase ``{"items": [<attachment>]}`` envelope carrying the created
        record - so the created attachment is returned directly and there is
        no need to re-list the entity's attachments to find it. The envelope
        is undocumented and therefore unguaranteed: a body this cannot parse
        raises ``ParseError`` rather than being returned unread, since a
        caller has no way to tell an unparsed body from a failed upload.

        Args:
            general_id: ID of the entity to attach the file to
            filename: Filename to store the upload under
            content: File content
            mime_type: Optional MIME type for the file part (omitted, the
                server infers one)

        Returns:
            The created attachment record, as the upload endpoint reports it

        Raises:
            ReadOnlyViolation: Client is in readonly mode
            ParseError: The response was not the single-item ``items``
                envelope this endpoint is recorded as sending.
            APIError: The server redirected instead of accepting the upload
                (see the class docstring), or another API error occurred.
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
        """
        self._client._check_write_permission()
        file_part = (filename, content, mime_type) if mime_type else (filename, content)
        body = await self._request_handler.upload_file(
            "/UploadFile.ashx",
            data={"generalid": str(general_id)},
            files={"file": file_part},
        )
        return self._parse_upload_response(body)

    @staticmethod
    def _parse_upload_response(body: str) -> UploadedAttachment:
        """Parse the ``/UploadFile.ashx`` envelope into the created record.

        Separated from ``upload`` so the envelope's shape can be exercised
        without a transport: the endpoint is undocumented, so every failure
        mode here is a guess about a real server's behaviour and wants a test
        of its own.

        Raises:
            ParseError: The body was not JSON, or not an ``items`` envelope
                holding exactly the one record a single-file upload creates.
        """
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ParseError(
                "upload response was not JSON; an HTML login page is one way this "
                "happens, TargetProcess documenting its file endpoints against "
                "Basic auth"
            ) from exc
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise ParseError(
                "upload response was not an 'items' envelope holding exactly one "
                f"record (got {type(payload).__name__} with keys "
                f"{sorted(payload) if isinstance(payload, dict) else 'n/a'})"
            )
        # Every field but ``id`` is optional, so without this a bare
        # ``{"id": 1}`` - or a record of some other type entirely - would
        # hydrate cleanly and be returned as a created attachment. The
        # endpoint is undocumented, which is the reason to check what it
        # claims to have made rather than the reason to trust it.
        resource_type = items[0].get("resourceType")
        if resource_type != "Attachment":
            raise ParseError(
                "upload response did not describe an Attachment "
                f"(resourceType was {resource_type!r})"
            )
        try:
            return UploadedAttachment.model_validate(items[0])
        except pydantic.ValidationError as exc:
            # Every other parse in the library surfaces a model-validation
            # failure as ParseError, and a caller guarding an upload with
            # ``except TargetProcessError`` would not catch pydantic's own.
            raise ParseError(f"failed to parse UploadedAttachment: {exc}") from exc
