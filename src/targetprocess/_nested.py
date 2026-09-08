"""Lightweight nested models embedded in entity payloads.

The shapes TP nests inside entity payloads rather than serving as entities in
their own right: the reference projections (:class:`EntityRef`,
:class:`UserRef`, :class:`RefWithImportance`), the embedded
:class:`CustomFieldValue` and :class:`CustomFieldConfig`, and the
``Items``-wrapped assignment collections. The entity models themselves live in
the sibling private modules and are re-exported, along with everything here, by
:mod:`targetprocess.models`.
"""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _unwrap_items(value: object) -> object:
    """Unwrap TP's ``{"Items": [...]}`` collection shape.

    Assignment-style collections (e.g. ``AssignedUser`` fetched via
    ``include=``) arrive wrapped in an ``Items`` envelope rather than as a
    bare list. Non-matching values (already a list, None) pass through for
    pydantic's own list handling.
    """
    if isinstance(value, dict) and "Items" in value:
        return value["Items"]
    return value


class CustomFieldValue(BaseModel):
    """A single custom-field value embedded in an entity's ``CustomFields``.

    TP has no queryable ``/CustomFieldValues`` collection; custom-field values
    arrive as ``{Name, Type, Value}`` elements inside each entity payload's
    ``CustomFields`` array. ``Value`` is polymorphic - a string, number,
    boolean, or null depending on the field's ``Type`` - so it is typed
    ``object`` to carry the wire value faithfully without lossy coercion.
    Date-typed values therefore stay as their raw ``/Date(ms±HHMM)/`` wire
    string; pass one through :func:`targetprocess.models.parse_tp_date` for a
    ``datetime``.

    Attributes:
        name: Custom-field name
        type: Custom-field type (e.g. "DropDown", "Number", "CheckBox")
        value: The field value (polymorphic; may be None)
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    name: str | None = Field(default=None, alias="Name", description="Custom-field name")
    type: str | None = Field(default=None, alias="Type", description="Custom-field type")
    value: object = Field(default=None, alias="Value", description="Field value (polymorphic)")


class CustomFieldConfig(BaseModel):
    """Type-specific configuration attached to a custom-field definition.

    ``CustomField.Config`` is a reference in TP's ``/meta`` but not an entity
    reference: it arrives as a bare settings object carrying no ``Id``, so
    :class:`EntityRef` cannot model it. Which keys are meaningful depends on
    the field's ``FieldType`` - a calculated field populates
    ``CalculationModel``, a numeric one ``Units`` and ``FormatSpecifier``.

    Attributes:
        default_value: Value TP applies when the field is left unset
        calculation_model: Expression driving a calculated field
        calculation_model_contains_collections: Whether that expression spans
            collections (TP evaluates those differently)
        units: Unit label rendered beside a numeric value
        format_specifier: Numeric/date format string
        format_info: Locale/format metadata accompanying the specifier
        editor_type: Editor TP renders for the field
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    default_value: str | None = Field(
        default=None, alias="DefaultValue", description="Default value"
    )
    calculation_model: str | None = Field(
        default=None, alias="CalculationModel", description="Calculation expression"
    )
    calculation_model_contains_collections: bool | None = Field(
        default=None,
        alias="CalculationModelContainsCollections",
        description="Calculation spans collections",
    )
    units: str | None = Field(default=None, alias="Units", description="Unit label")
    format_specifier: str | None = Field(
        default=None, alias="FormatSpecifier", description="Format string"
    )
    format_info: str | None = Field(default=None, alias="FormatInfo", description="Format metadata")
    editor_type: str | None = Field(default=None, alias="EditorType", description="Editor type")


class EntityRef(BaseModel):
    """Reference to another TargetProcess entity.

    Lightweight model for nested id+name-shaped entity references (Project,
    Team, EntityState, etc.). Pydantic aliases handle the API PascalCase
    format automatically. Extra keys the referenced entity may carry (e.g.
    Team's ``EmojiIcon``, EntityState's ``NumericPriority``, Project's
    nested ``Process``) are tolerated and ignored.

    Attributes:
        id: Unique identifier of the referenced entity
        name: Display name of the referenced entity
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    id: int = Field(alias="Id", description="Unique identifier")
    name: str | None = Field(default=None, alias="Name", description="Display name")


class EntityTypeRef(BaseModel):
    """Reference to a TP ``EntityType``, which can arrive without an ``Id``.

    Unlike every other reference, TP does not reliably identify this one. A
    ``UserStory`` carries the full ``{ResourceType, Id, Name,
    IsUnitInHourOnly}``, while a ``Bug`` or ``Task`` carries only
    ``{ResourceType, IsUnitInHourOnly}`` - no ``Id``, no ``Name``. So
    :class:`EntityRef`, whose ``Id`` is required, cannot model it: a required
    ``Id`` would fail the whole entity on a nested field TP chose not to
    populate.

    Both identifying fields are therefore optional, and a caller must treat
    either as possibly ``None``. The entity's own ``resource_type`` names the
    same type and is always present, so it is the reliable source for "what
    kind of thing is this".

    Attributes:
        id: Unique identifier of the entity type (absent on some types)
        name: Display name of the entity type (absent on some types)
        is_unit_in_hour_only: Whether the type's effort is hours-only
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    id: int | None = Field(default=None, alias="Id", description="Unique identifier")
    name: str | None = Field(default=None, alias="Name", description="Display name")
    is_unit_in_hour_only: bool | None = Field(
        default=None, alias="IsUnitInHourOnly", description="Effort is hours-only"
    )


class UserRef(BaseModel):
    """Reference to a User-shaped entity.

    Covers Owner/Creator/LastEditor/LastCommentedUser/AssignedUser-style
    fields, which TP shapes as ``{ResourceType, Id, FirstName, LastName,
    Login, FullName}`` - notably with no ``Name`` key.

    Attributes:
        id: Unique identifier of the referenced user
        resource_type: Type of the reference (typically "User")
        first_name: Referenced user's first name
        last_name: Referenced user's last name
        login: Referenced user's login
        full_name: Referenced user's full name
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    id: int = Field(alias="Id", description="Unique identifier")
    resource_type: str | None = Field(default=None, alias="ResourceType", description="Entity type")
    first_name: str | None = Field(default=None, alias="FirstName", description="First name")
    last_name: str | None = Field(default=None, alias="LastName", description="Last name")
    login: str | None = Field(default=None, alias="Login", description="Login")
    full_name: str | None = Field(default=None, alias="FullName", description="Full name")


class RefWithImportance(BaseModel):
    """Reference object carrying an Importance ranking.

    Shape used by ``Bug.severity`` / ``Bug.priority`` (and equivalent
    ``priority`` fields on other assignables): ``{ResourceType, Id, Name,
    Importance}`` rather than a bare scalar.

    Attributes:
        id: Unique identifier of the referenced entity
        resource_type: Type of the reference (e.g. "Severity", "Priority")
        name: Display name (e.g. "Blocking", "Urgent")
        importance: Importance ranking
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    id: int = Field(alias="Id", description="Unique identifier")
    resource_type: str | None = Field(default=None, alias="ResourceType", description="Entity type")
    name: str | None = Field(default=None, alias="Name", description="Display name")
    importance: int | None = Field(
        default=None, alias="Importance", description="Importance ranking"
    )


# Assignment collections (e.g. AssignedUser fetched via include=) arrive as
# {"Items": [...]} rather than a bare list or a single ref.
AssignedUsers = Annotated[list[UserRef], BeforeValidator(_unwrap_items)]
