"""The types that carry content attached to another entity.

A ``Comment`` and an ``Attachment`` both hang off a ``General``; a
``CustomField`` describes a field configured on a process rather than a value
held by an entity. None sits in TP's ``General`` hierarchy.

Re-exported by :mod:`targetprocess.models`, which stays the import surface
callers use.
"""

from pydantic import BaseModel, ConfigDict, Field

from targetprocess._base import Entity, NamedEntity
from targetprocess._dates import TPDateTime
from targetprocess._nested import CustomFieldConfig, EntityRef, EntityTypeRef, UserRef


class Comment(Entity):
    """Comment on a TP entity.

    TP comments carry the comment body in ``Description`` and have no Name
    field. ``General`` is the entity the comment is attached to; ``Owner`` is
    the commenter. Threaded replies carry a ``ParentId``.

    Attributes:
        description: Comment body text
        parent_id: Parent comment id for threaded replies (None at top level)
        description_modify_date: When the comment body was last edited
        is_private: Whether the comment is private
        is_pinned: Whether the comment is pinned
        general: The entity the comment is attached to
        owner: The commenter
        entity_version: TP's per-record version counter (increments on edit)
    """

    description: str | None = Field(
        default=None, alias="Description", description="Comment body text"
    )
    parent_id: int | None = Field(
        default=None, alias="ParentId", description="Parent comment id (threaded replies)"
    )
    description_modify_date: TPDateTime | None = Field(
        default=None, alias="DescriptionModifyDate", description="When the body was last edited"
    )
    is_private: bool | None = Field(
        default=None, alias="IsPrivate", description="Whether the comment is private"
    )
    is_pinned: bool | None = Field(
        default=None, alias="IsPinned", description="Whether the comment is pinned"
    )
    general: EntityRef | None = Field(
        default=None, alias="General", description="Attached-to entity"
    )
    owner: UserRef | None = Field(default=None, alias="Owner", description="Commenter")
    entity_version: int | None = Field(
        default=None, alias="EntityVersion", description="Per-record version counter"
    )


class Attachment(NamedEntity):
    """File attachment on a TP entity.

    ``Name`` is the display filename; ``UniqueFileName`` is TP's stored name.
    ``General`` is the entity the file is attached to; ``Owner`` is the
    uploader. ``Uri`` is the download path for the file's bytes (relative to
    the instance root, e.g. ``/Attachment.aspx?AttachmentID=1234``) - fetch it
    via ``client.attachments.download``.

    Attributes:
        unique_file_name: TP's stored unique filename
        description: Attachment description
        date: Upload date/time
        owner: The uploader
        general: The entity the file is attached to
        message: Optional attachment message
        uri: Download path for the file bytes, relative to the instance root
        mime_type: MIME type of the stored file
        size: File size in bytes
        thumbnail_uri: Download path for the thumbnail (images only)
    """

    unique_file_name: str | None = Field(
        default=None, alias="UniqueFileName", description="Stored unique filename"
    )
    description: str | None = Field(
        default=None, alias="Description", description="Attachment description"
    )
    date: TPDateTime | None = Field(default=None, alias="Date", description="Upload date/time")
    owner: UserRef | None = Field(default=None, alias="Owner", description="Uploader")
    general: EntityRef | None = Field(
        default=None, alias="General", description="Attached-to entity"
    )
    message: EntityRef | None = Field(
        default=None, alias="Message", description="Attachment message"
    )
    uri: str | None = Field(
        default=None, alias="Uri", description="Download path for the file bytes"
    )
    mime_type: str | None = Field(default=None, alias="MimeType", description="MIME type")
    size: int | None = Field(default=None, alias="Size", ge=0, description="File size in bytes")
    thumbnail_uri: str | None = Field(
        default=None, alias="ThumbnailUri", description="Thumbnail download path"
    )


class UploadedFileRef(BaseModel):
    """A reference nested in an ``/UploadFile.ashx`` response.

    The same three roles :class:`Attachment` names - the uploader, the entity
    the file landed on, and that entity as an Assignable - but projected by
    the file endpoint rather than the JSON entity API, so the keys are
    camelCase and the user shape carries its name fields inline. One
    permissive model covers all of them: a user reference brings the name
    fields, an entity reference brings ``name``, and ``extra="allow"`` keeps
    anything else the endpoint sends.

    Not in ``_nested`` with the other reference shapes on purpose: those
    project TP's JSON entity API, and this one does not (see
    :class:`UploadedAttachment`).

    Attributes:
        resource_type: Type of the referenced record
        id: Id of the referenced record
        name: Display name, on an entity reference
        first_name: Given name, on a user reference
        last_name: Family name, on a user reference
        full_name: Display name, on a user reference
        login: Login, on a user reference
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="allow",
    )

    resource_type: str | None = Field(
        default=None, alias="resourceType", description="Referenced record's type"
    )
    id: int | None = Field(default=None, alias="id", description="Referenced record's Id")
    name: str | None = Field(default=None, alias="name", description="Display name")
    first_name: str | None = Field(default=None, alias="firstName", description="Given name")
    last_name: str | None = Field(default=None, alias="lastName", description="Family name")
    full_name: str | None = Field(default=None, alias="fullName", description="Display name")
    login: str | None = Field(default=None, alias="login", description="Login")


class UploadedAttachment(BaseModel):
    """The attachment record ``/UploadFile.ashx`` answers an upload with.

    TargetProcess documents neither this endpoint's response body nor its
    casing. What it actually sends - recorded in the write-path integration
    suite rather than taken on trust - is
    ``{"items": [<this shape>]}``: the created Attachment, hydrated much as
    ``/api/v1/Attachments`` would hydrate it, but in **camelCase** and with
    two extra fields the entity API does not carry (``persistedMimeType``,
    ``persistedSize``) alongside their entity-API equivalents. ``date`` is
    ISO-8601 rather than TP's ``/Date(ms±HHMM)/`` wire format, which
    :data:`TPDateTime` passes through to pydantic unchanged.

    Deliberately outside ``scripts/check_model_coverage.py``'s ``COLLECTIONS``
    map: this is one endpoint's response projection, not a queryable entity
    type, so there is no ``/meta`` to diff it against. The recorded cassette
    is what pins the shape.

    Attributes:
        resource_type: Always ``"Attachment"``
        id: Id of the created attachment record
        name: Display filename, as sent
        unique_file_name: TP's stored unique filename
        description: Attachment description (the filename, by default)
        date: Upload timestamp
        persisted_mime_type: MIME type of the stored file
        persisted_size: Stored size in bytes
        is_empty: Whether the stored file has no content
        uri: Absolute download URL for the file bytes
        thumbnail_uri: Absolute download URL for the thumbnail
        mime_type: MIME type of the stored file
        size: File size in bytes
        owner: The uploader
        general: The entity the file was attached to
        message: The message the file was attached to, if any
        assignable: The attached-to entity as an Assignable, if it is one
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="allow",
    )

    resource_type: str | None = Field(default=None, alias="resourceType", description="Record type")
    id: int = Field(alias="id", description="Created attachment's Id")
    name: str | None = Field(default=None, alias="name", description="Display filename")
    unique_file_name: str | None = Field(
        default=None, alias="uniqueFileName", description="Stored unique filename"
    )
    description: str | None = Field(
        default=None, alias="description", description="Attachment description"
    )
    date: TPDateTime | None = Field(default=None, alias="date", description="Upload timestamp")
    persisted_mime_type: str | None = Field(
        default=None, alias="persistedMimeType", description="Stored MIME type"
    )
    persisted_size: int | None = Field(
        default=None, alias="persistedSize", ge=0, description="Stored size in bytes"
    )
    is_empty: bool | None = Field(
        default=None, alias="isEmpty", description="Whether the stored file is empty"
    )
    uri: str | None = Field(default=None, alias="uri", description="Absolute download URL")
    thumbnail_uri: str | None = Field(
        default=None, alias="thumbnailUri", description="Absolute thumbnail URL"
    )
    mime_type: str | None = Field(default=None, alias="mimeType", description="MIME type")
    size: int | None = Field(default=None, alias="size", ge=0, description="File size in bytes")
    owner: UploadedFileRef | None = Field(default=None, alias="owner", description="Uploader")
    general: UploadedFileRef | None = Field(
        default=None, alias="general", description="Attached-to entity"
    )
    message: UploadedFileRef | None = Field(
        default=None, alias="message", description="Attached-to message"
    )
    assignable: UploadedFileRef | None = Field(
        default=None, alias="assignable", description="Attached-to entity as an Assignable"
    )


class CustomField(NamedEntity):
    """Custom-field definition (the queryable ``/CustomFields`` entity).

    Describes a custom field configured on a Process/EntityType - its type,
    constraints, and metadata. Actual per-entity values are carried by
    ``CustomFieldValue`` (embedded in each entity's ``CustomFields`` array),
    not here.

    Attributes:
        value: Field value from the definition endpoint (typically a string or
            None; typed ``object`` to carry any value the endpoint returns)
        field_type: Field type (e.g. "DropDown", "Text", "Date", "Number")
        enabled_for_filter: Whether the field is enabled for filtering
        required: Whether the field is required
        numeric_priority: Ordering priority
        is_system: Whether this is a system field
        description: Field description
        placeholder: Field placeholder text
        max_text_length: Maximum text length
        entity_field_name: Underlying entity field name, where the custom field
            shadows a built-in one
        config: Type-specific configuration (default value, units, formatting)
        entity_type: EntityType the field applies to
        process: Process the field belongs to
    """

    value: object = Field(default=None, alias="Value", description="Field value (polymorphic)")
    field_type: str | None = Field(default=None, alias="FieldType", description="Field type")
    enabled_for_filter: bool | None = Field(
        default=None, alias="EnabledForFilter", description="Enabled for filtering"
    )
    required: bool | None = Field(default=None, alias="Required", description="Whether required")
    numeric_priority: float | None = Field(
        default=None, alias="NumericPriority", description="Ordering priority"
    )
    is_system: bool | None = Field(
        default=None, alias="IsSystem", description="Whether a system field"
    )
    description: str | None = Field(
        default=None, alias="Description", description="Field description"
    )
    placeholder: str | None = Field(
        default=None, alias="Placeholder", description="Placeholder text"
    )
    max_text_length: int | None = Field(
        default=None, alias="MaxTextLength", description="Maximum text length"
    )
    entity_field_name: str | None = Field(
        default=None, alias="EntityFieldName", description="Shadowed entity field name"
    )
    config: CustomFieldConfig | None = Field(
        default=None, alias="Config", description="Type-specific configuration"
    )
    entity_type: EntityTypeRef | None = Field(
        default=None, alias="EntityType", description="Applicable entity type"
    )
    process: EntityRef | None = Field(default=None, alias="Process", description="Owning process")
