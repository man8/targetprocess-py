"""Resource managers for TargetProcess entities."""

from targetprocess_py.resources.assignables import AssignableResource
from targetprocess_py.resources.assignments import AssignmentsResource
from targetprocess_py.resources.attachments import AttachmentsResource
from targetprocess_py.resources.base import BaseResource
from targetprocess_py.resources.bugs import BugsResource
from targetprocess_py.resources.comments import CommentsResource
from targetprocess_py.resources.custom_activities import CustomActivitiesResource
from targetprocess_py.resources.custom_fields import CustomFieldsResource
from targetprocess_py.resources.custom_rules import CustomRulesResource
from targetprocess_py.resources.entities import EntitiesResource
from targetprocess_py.resources.entity_states import EntityStatesResource
from targetprocess_py.resources.entity_types import EntityTypesResource
from targetprocess_py.resources.epics import EpicsResource
from targetprocess_py.resources.features import FeaturesResource
from targetprocess_py.resources.iterations import IterationsResource
from targetprocess_py.resources.priorities import PrioritiesResource
from targetprocess_py.resources.processes import ProcessesResource
from targetprocess_py.resources.projects import ProjectsResource
from targetprocess_py.resources.relation_types import RelationTypesResource
from targetprocess_py.resources.relations import RelationsResource
from targetprocess_py.resources.releases import ReleasesResource
from targetprocess_py.resources.requests import RequestsResource
from targetprocess_py.resources.role_efforts import RoleEffortsResource
from targetprocess_py.resources.roles import RolesResource
from targetprocess_py.resources.severities import SeveritiesResource
from targetprocess_py.resources.tasks import TasksResource
from targetprocess_py.resources.team_assignments import TeamAssignmentsResource
from targetprocess_py.resources.team_iterations import TeamIterationsResource
from targetprocess_py.resources.teams import TeamsResource
from targetprocess_py.resources.terms import TermsResource
from targetprocess_py.resources.test_cases import TestCasesResource
from targetprocess_py.resources.times import TimesResource
from targetprocess_py.resources.user_stories import UserStoriesResource
from targetprocess_py.resources.users import UsersResource
from targetprocess_py.resources.workflows import WorkflowsResource

__all__ = [
    # Base
    "BaseResource",
    "AssignableResource",
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
