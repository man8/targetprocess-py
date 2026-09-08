"""Tests for the declared field surface.

Each model must declare the value and reference properties TP's
``/api/v1/{collection}/meta`` names for its type. These tests pin that surface
against live-shaped payloads captured from TP ``2608.2.0.3147``: a field that
silently stopped parsing - a wrong alias, a base class dropped in a refactor -
would otherwise show up only as a ``None`` at a call site.

``scripts/check_model_coverage.py`` measures the same thing against a live
instance; these tests are its offline counterpart, and need no token.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from targetprocess import ClientMode, TargetProcessClient
from targetprocess.models import (
    AssignableEntity,
    Attachment,
    Bug,
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
    Process,
    Project,
    Relation,
    Release,
    Request,
    Role,
    Severity,
    Task,
    Team,
    TeamIteration,
    Term,
    Time,
    User,
    UserStory,
    Workflow,
)
from targetprocess.models import TestCase as TPTestCase
from targetprocess.request_handler import RequestHandler
from targetprocess.resources.user_stories import UserStoriesResource
from tests.live_payloads import (
    LIVE_BUG_PARTIAL_ENTITY_TYPE,
    LIVE_TASK_PARTIAL_ENTITY_TYPE,
    LIVE_USER_STORY,
)

# The six Assignable types and the fields TP declares on that base.
ASSIGNABLE_TYPES = [UserStory, Bug, Task, Feature, Epic, Request]
GENERAL_TYPES = [Project, Team, Release, Iteration, TeamIteration, TPTestCase]

ASSIGNABLE_BASE_FIELDS = [
    "effort",
    "effort_completed",
    "effort_todo",
    "progress",
    "time_spent",
    "time_remain",
    "units",
    "lead_time",
    "cycle_time",
    "last_state_change_date",
    "planned_start_date",
    "planned_end_date",
    "forecast_end_date",
    "entity_state",
    "priority",
    "release",
    "iteration",
    "team_iteration",
    "team",
    "responsible_team",
    "assigned_user",
]

GENERAL_BASE_FIELDS = [
    "description",
    "tags",
    "start_date",
    "end_date",
    "last_comment_date",
    "numeric_priority",
    "entity_version",
    "is_now",
    "is_next",
    "is_previous",
    "entity_type",
    "owner",
    "creator",
    "last_editor",
    "last_commented_user",
    "project",
    "linked_test_plan",
    "milestone",
]


def test_hierarchy_mirrors_targetprocess() -> None:
    # TP's /meta declares Assignable as a subtype of General; the models say so
    # too, which is what lets each shared field be declared exactly once.
    assert issubclass(AssignableEntity, GeneralEntity)
    assert issubclass(GeneralEntity, Entity)


@pytest.mark.parametrize("model", ASSIGNABLE_TYPES, ids=lambda m: m.__name__)
@pytest.mark.parametrize("field", ASSIGNABLE_BASE_FIELDS)
def test_every_assignable_declares_the_assignable_base_fields(
    model: type[AssignableEntity], field: str
) -> None:
    assert field in model.model_fields


@pytest.mark.parametrize("model", ASSIGNABLE_TYPES + GENERAL_TYPES, ids=lambda m: m.__name__)
@pytest.mark.parametrize("field", GENERAL_BASE_FIELDS)
def test_every_general_declares_the_general_base_fields(
    model: type[GeneralEntity], field: str
) -> None:
    assert field in model.model_fields


def test_live_user_story_parses_the_full_field_surface() -> None:
    us = UserStory.model_validate(LIVE_USER_STORY)

    # Values
    assert us.tags == "Provider: Example, Country: XX"
    assert us.numeric_priority == pytest.approx(63745.18191507797)
    assert us.entity_version == 48630098
    assert us.is_now is False
    assert us.time_spent == 0.5
    assert us.initial_estimate == 0.0
    assert us.units == "h"
    assert us.lead_time == pytest.approx(0.37221218513194443)
    assert us.last_state_change_date is not None
    assert us.last_state_change_date.year == 2026

    # Nothing fell through to extras.
    assert us.model_extra == {}


def test_live_user_story_parses_each_reference_into_its_own_shape() -> None:
    us = UserStory.model_validate(LIVE_USER_STORY)

    # GeneralUser-shaped references carry no Name, so they must be UserRefs.
    assert us.creator is not None
    assert us.creator.full_name == "Alex Example"
    assert us.creator.login == "alex@example.com"
    assert us.owner is not None and us.owner.id == 342
    assert us.last_editor is not None and us.last_editor.id == 342

    # Priority carries an Importance, so it must be a RefWithImportance.
    assert us.priority is not None
    assert us.priority.name == "Nice To Have"
    assert us.priority.importance == 5

    # Plain {Id, Name} references.
    assert us.entity_type is not None and us.entity_type.name == "UserStory"
    assert us.entity_state is not None and us.entity_state.name == "Plan"
    assert us.team is not None and us.team.name == "Example Team"

    # ResponsibleTeam arrives with an Id and no Name at all.
    assert us.responsible_team is not None
    assert us.responsible_team.id == 82050
    assert us.responsible_team.name is None


def test_numeric_priority_is_not_the_priority_reference() -> None:
    # The two are easy to conflate and are different things: one is TP's
    # continuous backlog rank, the other the entity-type-scoped Priority record.
    us = UserStory.model_validate(LIVE_USER_STORY)
    assert isinstance(us.numeric_priority, float)
    assert us.priority is not None
    assert us.priority.importance == 5


def test_bug_keeps_severity_alongside_the_inherited_priority() -> None:
    bug = Bug.model_validate(
        {
            "Id": 74436,
            "Severity": {
                "ResourceType": "Severity",
                "Id": 5,
                "Name": "Enhancement",
                "Importance": 5,
            },
            "Priority": {
                "ResourceType": "Priority",
                "Id": 7,
                "Name": "Fix If Time",
                "Importance": 2,
            },
            "UserStory": {"Id": 73678, "Name": "Sample parent story"},
            "Feature": {"Id": 73677, "Name": "Sample feature"},
        }
    )
    assert bug.severity is not None and bug.severity.name == "Enhancement"
    assert bug.priority is not None and bug.priority.name == "Fix If Time"
    assert bug.user_story is not None and bug.user_story.id == 73678
    assert bug.feature is not None and bug.feature.id == 73677


def test_entity_type_reference_parses_without_an_id() -> None:
    # TP does not identify this reference uniformly: a UserStory's EntityType
    # carries {Id, Name}, a Bug's and a Task's carry neither. A shape requiring
    # an Id would fail the whole entity on a nested field TP chose not to
    # populate - which is every Bug and every Task.
    bug = Bug.model_validate(LIVE_BUG_PARTIAL_ENTITY_TYPE)
    assert bug.entity_type is not None
    assert bug.entity_type.id is None
    assert bug.entity_type.name is None
    assert bug.entity_type.is_unit_in_hour_only is False
    # The rest of the record still parses.
    assert bug.name == "Sample bug"
    assert bug.severity is not None and bug.severity.name == "Enhancement"

    task = Task.model_validate(LIVE_TASK_PARTIAL_ENTITY_TYPE)
    assert task.entity_type is not None
    assert task.entity_type.id is None
    assert task.entity_type.is_unit_in_hour_only is True
    assert task.parent is not None and task.parent.id == 5099


def test_entity_type_reference_still_parses_a_fully_identified_one() -> None:
    # The optional Id must not weaken the case where TP does send it.
    us = UserStory.model_validate(LIVE_USER_STORY)
    assert us.entity_type is not None
    assert us.entity_type.id == 4
    assert us.entity_type.name == "UserStory"


def test_resource_type_is_the_reliable_type_discriminator() -> None:
    # Because EntityType.name can be absent, the entity's own resource_type is
    # what a caller should branch on.
    bug = Bug.model_validate(LIVE_BUG_PARTIAL_ENTITY_TYPE)
    assert bug.entity_type is not None and bug.entity_type.name is None
    assert bug.resource_type == "Bug"


def test_task_has_no_initial_estimate_or_build() -> None:
    # TP declares neither on Task; declaring them anyway would invent a field.
    assert "initial_estimate" not in Task.model_fields
    assert "build" not in Task.model_fields


def test_request_declares_its_inbound_fields() -> None:
    request = Request.model_validate(
        {
            "Id": 75385,
            "SourceType": "None",
            "IsReplied": True,
            "IsPrivate": False,
            "VotesCount": 1,
            "RequestType": {"ResourceType": "RequestType", "Id": 4, "Name": "Enhancement"},
        }
    )
    assert request.source_type == "None"
    assert request.is_replied is True
    assert request.is_private is False
    assert request.votes_count == 1
    assert request.request_type is not None and request.request_type.name == "Enhancement"


def test_test_case_declares_its_run_status_fields() -> None:
    case = TPTestCase.model_validate(
        {
            "Id": 24150,
            "LastRunStatus": "Passed",
            "LastStatus": True,
            "LastRunDate": "/Date(1563365112000+0200)/",
            "LastFailureComment": None,
            "Priority": {"ResourceType": "Priority", "Id": 25, "Name": "Moderate", "Importance": 3},
        }
    )
    assert case.last_run_status == "Passed"
    assert case.last_status is True
    assert case.last_run_date is not None and case.last_run_date.year == 2019
    assert case.priority is not None and case.priority.importance == 3


def test_project_declares_its_roll_up_and_branding_fields() -> None:
    project = Project.model_validate(
        {
            "Id": 33585,
            "Name": "Example Project",
            "Effort": 12.0,
            "IsActive": True,
            "IsProduct": False,
            "Abbreviation": "CC",
            "MailReplyAddress": "cc@example.invalid",
            "Color": "#336699",
            "EntityState": {"Id": 79, "Name": "Plan"},
            "Process": {"ResourceType": "Process", "Id": 2, "Name": "Dev Kanban/Scrum"},
            "Company": {"Id": 1, "Name": "Acme"},
        }
    )
    assert project.effort == 12.0
    assert project.is_active is True
    assert project.abbreviation == "CC"
    assert project.color == "#336699"
    assert project.entity_state is not None and project.entity_state.name == "Plan"
    assert project.process is not None and project.process.name == "Dev Kanban/Scrum"
    assert project.company is not None and project.company.name == "Acme"


def test_team_declares_its_icon_fields() -> None:
    team = Team.model_validate(
        {"Id": 33091, "Name": "Example Team", "EmojiIcon": ":calling:", "IsActive": True}
    )
    assert team.emoji_icon == ":calling:"
    assert team.is_active is True
    assert team.model_extra == {}


def test_user_declares_its_capacity_and_identity_fields() -> None:
    user = User.model_validate(
        {
            "Id": 1,
            "Login": "alex.example",
            "FullName": "Alex Example",
            "IsAdministrator": True,
            "IsObserver": False,
            "Kind": "User",
            "RichEditor": "Markdown",
            "GlobalId": "A1B2C3D4-5E6F-4A7B-8C9D-0E1F2A3B4C5D",
            "WeeklyAvailableHours": 30.0,
            "CurrentAllocation": 100,
            "LastLoginDate": "/Date(1700000000000+0200)/",
            "PasswordHashAlgorithm": "IdentityV3",
            "Role": {"ResourceType": "Role", "Id": 10, "Name": "Sys Admin"},
        }
    )
    assert user.is_administrator is True
    assert user.kind == "User"
    assert user.rich_editor == "Markdown"
    assert user.weekly_available_hours == 30.0
    assert user.current_allocation == 100
    assert user.last_login_date is not None
    assert user.role is not None and user.role.name == "Sys Admin"
    assert user.model_extra == {}


def test_user_does_not_declare_password() -> None:
    # TP marks Password unreadable (CanGet: false). Leaving it undeclared keeps
    # a password-shaped attribute out of model_dump; a supplied one is still
    # carried, as an extra, so a write path is not blocked.
    assert "password" not in User.model_fields
    user = User.model_validate({"Id": 1, "Password": "secret"})
    assert "password" not in user.model_dump()
    assert user.model_extra == {"Password": "secret"}


def test_relation_declares_both_direction_pairs() -> None:
    relation = Relation.model_validate(
        {
            "Id": 1,
            "Master": {"ResourceType": "General", "Id": 76, "Name": "Blocking"},
            "Slave": {"ResourceType": "General", "Id": 75, "Name": "Blocked"},
            "Inbound": {"ResourceType": "General", "Id": 76, "Name": "Blocking"},
            "Outbound": {"ResourceType": "General", "Id": 75, "Name": "Blocked"},
            "RelationType": {"Id": 3, "Name": "Relation"},
        }
    )
    # TP sends the same pair under both names; Inbound mirrors Master.
    assert relation.inbound is not None and relation.master is not None
    assert relation.inbound.id == relation.master.id == 76
    assert relation.outbound is not None and relation.slave is not None
    assert relation.outbound.id == relation.slave.id == 75


def test_custom_field_config_parses_without_an_id() -> None:
    # Config is a reference in /meta but carries no Id, so EntityRef cannot
    # model it - a regression here would raise rather than return None.
    field = CustomField.model_validate(
        {
            "Id": 9,
            "Name": "RequestorDepartment",
            "FieldType": "DropDown",
            "EntityFieldName": "[DEPRECATED]",
            "Config": {
                "ResourceType": "CustomFieldConfig",
                "DefaultValue": "500",
                "CalculationModel": "",
                "CalculationModelContainsCollections": None,
                "Units": "h",
                "FormatSpecifier": None,
                "EditorType": None,
            },
        }
    )
    assert field.entity_field_name == "[DEPRECATED]"
    assert field.config is not None
    assert field.config.default_value == "500"
    assert field.config.units == "h"
    assert field.config.calculation_model_contains_collections is None


def test_time_narrow_back_references_are_all_declared() -> None:
    for field in (
        "user_story",
        "task",
        "bug",
        "request",
        "test_plan",
        "test_plan_run",
        "custom_activity",
    ):
        assert field in Time.model_fields


def test_role_declares_its_permission_flags() -> None:
    role = Role.model_validate(
        {
            "Id": 20,
            "Name": "Account Specialist",
            "Description": "Adds customer-facing comments",
            "HasEffort": True,
            "CanChangeOwner": False,
            "CanPrioritize": False,
            "CanUsePersonalAccessTokens": True,
            "TimeSheetAccess": True,
        }
    )
    assert role.description == "Adds customer-facing comments"
    assert role.has_effort is True
    assert role.can_change_owner is False
    assert role.can_use_personal_access_tokens is True
    assert role.time_sheet_access is True
    assert role.model_extra == {}


def test_entity_state_declares_its_flags_and_references() -> None:
    state = EntityState.model_validate(
        {
            "Id": 284,
            "Name": "Open",
            "IsCommentRequired": False,
            "NumericPriority": 0.0,
            "EntityType": {"ResourceType": "EntityType", "Id": 8, "Name": "Bug"},
            "Process": {"ResourceType": "Process", "Id": 10, "Name": "SysAdmin"},
            "Workflow": {"ResourceType": "Workflow", "Id": 73, "Name": "Project workflow"},
            "ParentEntityState": None,
            "Role": None,
        }
    )
    assert state.is_comment_required is False
    assert state.numeric_priority == 0.0
    assert state.entity_type is not None and state.entity_type.name == "Bug"
    assert state.process is not None and state.process.name == "SysAdmin"
    assert state.workflow is not None and state.workflow.name == "Project workflow"
    assert state.parent_entity_state is None
    assert state.role is None
    assert state.model_extra == {}


@pytest.mark.parametrize(
    "field",
    ["effort", "effort_completed", "effort_todo", "time_spent", "time_remain", "initial_estimate"],
)
def test_server_supplied_numbers_carry_no_range_constraint(field: str) -> None:
    # A range constraint on a value TP computes fails the WHOLE entity, not the
    # field - one out-of-range roll-up would abort a whole list() page with a
    # ParseError. TP documents no bounds on these, so the read model reports
    # what arrived rather than asserting an invariant the API never promised.
    alias = UserStory.model_fields[field].alias
    assert alias is not None
    us = UserStory.model_validate({"Id": 1, alias: -1.0})
    assert getattr(us, field) == -1.0


def test_a_negative_roll_up_does_not_abort_the_entity() -> None:
    # The failure mode the absent constraint exists to avoid: the rest of the
    # record must still parse.
    project = Project.model_validate({"Id": 1, "Name": "P", "EffortToDo": -3.0, "IsActive": True})
    assert project.effort_todo == -3.0
    assert project.name == "P"
    assert project.is_active is True


@pytest.mark.asyncio
async def test_resource_get_returns_the_expanded_field_surface() -> None:
    """A resource fetch hydrates the new fields, not just the model in isolation."""
    mock_client = Mock(spec=TargetProcessClient)
    mock_client.mode = ClientMode.READONLY
    mock_request_handler = AsyncMock(spec=RequestHandler)
    mock_request_handler.get.return_value = LIVE_USER_STORY

    resource = UserStoriesResource(mock_client, mock_request_handler)
    us = await resource.get(75380)

    assert us.tags == "Provider: Example, Country: XX"
    assert us.creator is not None and us.creator.full_name == "Alex Example"
    assert us.priority is not None and us.priority.importance == 5
    assert us.time_spent == 0.5
    mock_request_handler.get.assert_awaited_once()


def test_attachment_message_is_an_entity_reference() -> None:
    # TP's /meta declares Message a complex reference (Type: "Message"), not a
    # string. Every live sample is null, so the populated shape is pinned here
    # from the declared type rather than from an observed payload.
    attachment = Attachment.model_validate(
        {
            "Id": 1,
            "Name": "screenshot.png",
            "Message": {"ResourceType": "Message", "Id": 7, "Name": "Inbound mail"},
        }
    )
    assert attachment.message is not None
    assert attachment.message.id == 7
    assert attachment.message.name == "Inbound mail"


def test_attachment_message_tolerates_the_common_null() -> None:
    attachment = Attachment.model_validate({"Id": 1, "Name": "f.log", "Message": None})
    assert attachment.message is None


# The value and reference properties each lookup/configuration type's /meta
# declares (TP 2608.2.0.3147), read with a read-only token. The offline twin of
# scripts/check_model_coverage.py for these types: every property must be
# declared, and nothing may be declared beyond them except the Entity base
# envelope, which stays None on a type whose /meta omits it.
LOOKUP_META_PROPERTIES: dict[type[Entity], set[str]] = {
    Severity: {"Id", "Name", "Importance", "IsDefault", "IsMostImportant", "IsLeastImportant"},
    Process: {"Id", "Name", "IsDefault", "Description"},
    Workflow: {"Id", "Name", "Process", "EntityType", "ParentWorkflow"},
    EntityType: {
        "Id",
        "Name",
        "CustomFieldScope",
        "IsSearchable",
        "IsUnitInHourOnly",
        "IsAssignable",
        "IsGlobal",
        "IsTeamAssignable",
        "HierarchyLevel",
        "HasAuditHistory",
        "IsExtendable",
    },
    Term: {"Id", "WordKey", "Value", "Process", "EntityType"},
    CustomActivity: {"Id", "Name", "Created", "Estimate", "Project", "User"},
    CustomRule: {"Id", "Name", "Description", "IsEnabled"},
}

ENTITY_BASE_ENVELOPE = {"ResourceType", "CreateDate", "ModifyDate", "CustomFields"}


@pytest.mark.parametrize(
    ("model", "properties"),
    LOOKUP_META_PROPERTIES.items(),
    ids=lambda v: getattr(v, "__name__", ""),
)
def test_lookup_model_declares_exactly_its_meta_surface(
    model: type[Entity], properties: set[str]
) -> None:
    declared = {field.alias or name for name, field in model.model_fields.items()}
    assert properties <= declared, f"undeclared: {sorted(properties - declared)}"
    assert declared - properties <= ENTITY_BASE_ENVELOPE, (
        f"declared but absent from /meta: {sorted(declared - properties - ENTITY_BASE_ENVELOPE)}"
    )


def test_term_carries_no_name() -> None:
    # /meta declares WordKey and Value but no Name, so Term extends Entity, not
    # NamedEntity: a Name attribute here would invent a field.
    assert "name" not in Term.model_fields
    term = Term.model_validate({"Id": 3, "WordKey": "UserStory", "Value": "Ticket"})
    assert term.word_key == "UserStory"
    assert term.value == "Ticket"
    assert not hasattr(term, "name")
