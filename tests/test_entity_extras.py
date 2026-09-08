"""Regression tests for the entity ``extra="allow"`` policy.

Entity models must not silently discard undeclared API fields: undeclared
keys are preserved in ``model_extra``, ``CustomFields`` parses into
``custom_fields`` on every entity, and a live-shaped payload round-trips
through ``model_dump(by_alias=True)`` without loss.
"""

from datetime import datetime

import pytest

from targetprocess import models
from targetprocess.models import (
    AssignableEntity,
    Assignment,
    Attachment,
    Bug,
    Comment,
    CustomActivity,
    CustomField,
    CustomFieldValue,
    CustomRule,
    Entity,
    EntityState,
    EntityType,
    Epic,
    Feature,
    GeneralEntity,
    Iteration,
    NamedEntity,
    Priority,
    Process,
    Project,
    Relation,
    RelationType,
    Release,
    Request,
    Role,
    RoleEffort,
    Severity,
    Task,
    Team,
    TeamAssignment,
    TeamIteration,
    Term,
    Time,
    User,
    UserStory,
    Workflow,
    format_tp_date,
)
from targetprocess.models import (
    TestCase as TPTestCase,  # aliased so pytest does not try to collect it
)
from tests.live_payloads import LIVE_USER_STORY, UNDECLARED_KEYS

# Live-shaped fixture: the payload the extras policy was settled against
# (UserStory 75041 fetched with
# include=[Id,Name,CustomFields,Tags,TimeSpent,NumericPriority] against
# TP 2608.2.0.3147). Since the models declared the full /meta field surface,
# Tags/TimeSpent/NumericPriority parse into typed attributes rather than into
# model_extra; UNDECLARED_KEYS below carries what still exercises the extras
# policy.
LIVE_SHAPED_USER_STORY = {
    "ResourceType": "UserStory",
    "Id": 75041,
    "Name": "Story with custom fields",
    "Project": {"Id": 4711, "Name": "Some Project"},
    "CustomFields": [
        {"Name": "BacklogPriority", "Type": "Number", "Value": 500.0},
        {"Name": "Type", "Type": "DropDown", "Value": "Dev"},
    ],
    "Tags": "royalty,ops",
    "TimeSpent": 4.0,
    "NumericPriority": 831.75,
}

ALL_ENTITY_TYPES = [
    AssignableEntity,
    Assignment,
    Attachment,
    Bug,
    Comment,
    CustomActivity,
    CustomField,
    CustomRule,
    Entity,
    EntityState,
    EntityType,
    Epic,
    Feature,
    GeneralEntity,
    Iteration,
    NamedEntity,
    Priority,
    Process,
    Project,
    Relation,
    RelationType,
    Release,
    Request,
    Role,
    RoleEffort,
    Severity,
    Task,
    Team,
    TeamAssignment,
    TeamIteration,
    Term,
    TPTestCase,
    Time,
    User,
    UserStory,
    Workflow,
]


def test_custom_fields_parsed_from_live_shaped_payload() -> None:
    us = UserStory.model_validate(LIVE_SHAPED_USER_STORY)
    assert us.custom_fields is not None
    assert [cfv.name for cfv in us.custom_fields] == ["BacklogPriority", "Type"]
    assert us.custom_fields[0].value == 500.0
    assert us.custom_fields[1].value == "Dev"
    assert all(isinstance(cfv, CustomFieldValue) for cfv in us.custom_fields)


def test_custom_fields_pascal_case_property() -> None:
    us = UserStory.model_validate(LIVE_SHAPED_USER_STORY)
    assert us.CustomFields is us.custom_fields


def test_undeclared_keys_preserved_in_model_extra() -> None:
    us = UserStory.model_validate(LIVE_SHAPED_USER_STORY | UNDECLARED_KEYS)
    assert us.model_extra is not None
    assert us.model_extra["Messages"] == {"Items": []}
    assert us.model_extra["Revisions"] == {"Items": []}
    assert us.model_extra["SomeFutureField"] == "kept"


def test_undeclared_keys_readable_as_attributes() -> None:
    # Pydantic exposes extras via attribute access, so undeclared API fields
    # stay reachable under their wire (PascalCase) names.
    us = UserStory.model_validate(LIVE_SHAPED_USER_STORY | UNDECLARED_KEYS)
    assert us.SomeFutureField == "kept"
    assert us.Messages == {"Items": []}


def test_declared_fields_do_not_land_in_model_extra() -> None:
    # The other half of the declared field surface: a field the model declares
    # parses into its typed attribute instead of being reachable only by wire
    # name.
    us = UserStory.model_validate(LIVE_SHAPED_USER_STORY)
    assert us.tags == "royalty,ops"
    assert us.time_spent == 4.0
    assert us.numeric_priority == 831.75
    assert us.model_extra == {}


def test_live_shaped_payload_round_trips_without_loss() -> None:
    us = UserStory.model_validate(LIVE_SHAPED_USER_STORY)
    dump = us.model_dump(by_alias=True)
    assert dump["CustomFields"] == LIVE_SHAPED_USER_STORY["CustomFields"]
    assert dump["Tags"] == LIVE_SHAPED_USER_STORY["Tags"]
    assert dump["TimeSpent"] == LIVE_SHAPED_USER_STORY["TimeSpent"]
    assert dump["NumericPriority"] == LIVE_SHAPED_USER_STORY["NumericPriority"]
    # Wholesale: every (key, value) pair of the wire payload survives the
    # round-trip - no key of the original is lost.
    assert LIVE_SHAPED_USER_STORY.items() <= dump.items()


def test_no_wire_key_is_lost_on_a_fully_hydrated_payload() -> None:
    # The thin fixture above carries no date and no rich reference, so it
    # cannot see the normalisations a real payload goes through. This uses the
    # fully-hydrated live record: keys must all survive even though values are
    # normalised to their declared types.
    us = UserStory.model_validate(LIVE_USER_STORY | UNDECLARED_KEYS)
    dump = us.model_dump(by_alias=True)
    lost = [key for key in (LIVE_USER_STORY | UNDECLARED_KEYS) if key not in dump]
    assert lost == []


def test_declared_values_are_normalised_not_echoed() -> None:
    # The three ways a dumped value legitimately differs from the wire value.
    # Pinned so a change to any of them is a decision, not a surprise.
    us = UserStory.model_validate(LIVE_USER_STORY)
    dump = us.model_dump(by_alias=True)

    # 1. A date parses to a datetime rather than staying the TP wire string.
    assert isinstance(LIVE_USER_STORY["StartDate"], str)
    assert isinstance(dump["StartDate"], datetime)
    assert format_tp_date(dump["StartDate"]) == LIVE_USER_STORY["StartDate"]

    # 2. A nested reference is projected onto its model's fields: a key the
    #    reference model does not declare is dropped, one it declares but the
    #    payload omitted comes back None.
    assert "ResourceType" in LIVE_USER_STORY["EntityState"]
    assert "ResourceType" not in dump["EntityState"]
    assert "FirstName" not in LIVE_USER_STORY["Owner"]
    assert dump["Owner"]["FirstName"] is None

    # 3. Whitespace is stripped, so a padded value does not survive verbatim.
    padded = UserStory.model_validate({"Id": 1, "Tags": "  a, b  "})
    assert padded.tags == "a, b"


def test_assignment_of_undeclared_attribute_lands_in_model_extra() -> None:
    # Deliberate consequence of extra="allow" + validate_assignment, recorded
    # in SPEC.md: assigning an undeclared attribute (a mistyped field name
    # included) does not raise; the value lands in model_extra and dumps.
    us = UserStory.model_validate({"Id": 1})
    us.efort = 3.0  # deliberately mistyped "effort"
    assert us.effort is None
    assert us.model_extra is not None
    assert us.model_extra["efort"] == 3.0
    assert us.model_dump()["efort"] == 3.0


def _discover_entity_types() -> set[type[Entity]]:
    """Return every Entity subclass the library defines, at any depth."""
    discovered: set[type[Entity]] = {Entity}
    stack: list[type[Entity]] = [Entity]
    while stack:
        for subclass in stack.pop().__subclasses__():
            if subclass.__module__.startswith("targetprocess.") and subclass not in discovered:
                discovered.add(subclass)
                stack.append(subclass)
    return discovered


def test_all_entity_types_list_is_complete() -> None:
    # "Every entity" must stay true as models are added: discover the real
    # Entity subclass tree and require ALL_ENTITY_TYPES to match it exactly.
    # The tree spans several private modules, so discovery walks the package
    # rather than one module - a model added in a new module still shows up.
    assert set(ALL_ENTITY_TYPES) == _discover_entity_types()


def test_every_entity_type_is_exported_from_models() -> None:
    # The definitions are split across private modules; targetprocess.models is
    # the single public import surface, and every model must be reachable
    # through it by name and listed in its __all__.
    for entity_type in _discover_entity_types():
        name = entity_type.__name__
        assert getattr(models, name, None) is entity_type, f"{name} not exported by models"
        assert name in models.__all__, f"{name} missing from models.__all__"


@pytest.mark.parametrize("entity_type", ALL_ENTITY_TYPES)
def test_custom_fields_reachable_on_every_entity(entity_type: type[Entity]) -> None:
    entity = entity_type.model_validate(
        {"Id": 1, "CustomFields": [{"Name": "X", "Type": "Text", "Value": "y"}]}
    )
    assert entity.custom_fields is not None
    assert entity.custom_fields[0].name == "X"
    assert entity.custom_fields[0].value == "y"


def test_fully_declared_payload_has_empty_extras() -> None:
    us = UserStory.model_validate({"Id": 9, "Name": "Plain", "ResourceType": "UserStory"})
    assert us.model_extra == {}
    assert us.custom_fields is None
