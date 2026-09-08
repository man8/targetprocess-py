"""Resource managers for TargetProcess entities."""

from targetprocess.resources.assignments import AssignmentsResource
from targetprocess.resources.attachments import AttachmentsResource
from targetprocess.resources.base import BaseResource
from targetprocess.resources.bugs import BugsResource
from targetprocess.resources.comments import CommentsResource
from targetprocess.resources.custom_activities import CustomActivitiesResource
from targetprocess.resources.custom_fields import CustomFieldsResource
from targetprocess.resources.custom_rules import CustomRulesResource
from targetprocess.resources.entities import EntitiesResource
from targetprocess.resources.entity_states import EntityStatesResource
from targetprocess.resources.entity_types import EntityTypesResource
from targetprocess.resources.epics import EpicsResource
from targetprocess.resources.features import FeaturesResource
from targetprocess.resources.iterations import IterationsResource
from targetprocess.resources.priorities import PrioritiesResource
from targetprocess.resources.processes import ProcessesResource
from targetprocess.resources.projects import ProjectsResource
from targetprocess.resources.relation_types import RelationTypesResource
from targetprocess.resources.relations import RelationsResource
from targetprocess.resources.releases import ReleasesResource
from targetprocess.resources.requests import RequestsResource
from targetprocess.resources.role_efforts import RoleEffortsResource
from targetprocess.resources.roles import RolesResource
from targetprocess.resources.severities import SeveritiesResource
from targetprocess.resources.tasks import TasksResource
from targetprocess.resources.team_assignments import TeamAssignmentsResource
from targetprocess.resources.team_iterations import TeamIterationsResource
from targetprocess.resources.teams import TeamsResource
from targetprocess.resources.terms import TermsResource
from targetprocess.resources.test_cases import TestCasesResource
from targetprocess.resources.times import TimesResource
from targetprocess.resources.user_stories import UserStoriesResource
from targetprocess.resources.users import UsersResource
from targetprocess.resources.workflows import WorkflowsResource

__all__ = [
    # Base
    "BaseResource",
    # Typed resources
    "AssignmentsResource",
    "AttachmentsResource",
    "BugsResource",
    "CommentsResource",
    "CustomActivitiesResource",
    "CustomFieldsResource",
    "CustomRulesResource",
    "EntityStatesResource",
    "EntityTypesResource",
    "EpicsResource",
    "FeaturesResource",
    "IterationsResource",
    "PrioritiesResource",
    "ProcessesResource",
    "ProjectsResource",
    "RelationTypesResource",
    "RelationsResource",
    "ReleasesResource",
    "RequestsResource",
    "RoleEffortsResource",
    "RolesResource",
    "SeveritiesResource",
    "TasksResource",
    "TeamAssignmentsResource",
    "TeamIterationsResource",
    "TeamsResource",
    "TermsResource",
    "TestCasesResource",
    "TimesResource",
    "UserStoriesResource",
    "UsersResource",
    "WorkflowsResource",
    # Generic resource
    "EntitiesResource",
]
