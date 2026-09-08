"""Data models for TargetProcess entities.

The public import surface for every model. The definitions live in private
sibling modules grouped as TP's own type hierarchy groups them - the base
classes in ``_base``, the ``Assignable`` work items in ``_assignables``, the
other ``General`` types in ``_generals``, the lookup, configuration and people
types in ``_lookups``, the join entities in ``_joins``, the attached-content types in
``_content``, and the nested reference shapes in ``_nested`` - so that no one
file has to carry the whole field surface. Import from here, not from those.

The ``/Date(ms±HHMM)/`` wire-format helpers (``TPDateTime``, ``parse_tp_date``,
``format_tp_date``) live in ``_dates`` and are re-exported here too.
"""

from targetprocess._assignables import Bug as Bug
from targetprocess._assignables import Epic as Epic
from targetprocess._assignables import Feature as Feature
from targetprocess._assignables import Request as Request
from targetprocess._assignables import Task as Task
from targetprocess._assignables import UserStory as UserStory
from targetprocess._base import AssignableEntity as AssignableEntity
from targetprocess._base import Entity as Entity
from targetprocess._base import GeneralEntity as GeneralEntity
from targetprocess._base import NamedEntity as NamedEntity
from targetprocess._content import Attachment as Attachment
from targetprocess._content import Comment as Comment
from targetprocess._content import CustomField as CustomField
from targetprocess._content import UploadedAttachment as UploadedAttachment
from targetprocess._content import UploadedFileRef as UploadedFileRef
from targetprocess._dates import TPDateTime as TPDateTime
from targetprocess._dates import format_tp_date as format_tp_date
from targetprocess._dates import parse_tp_date as parse_tp_date
from targetprocess._generals import Iteration as Iteration
from targetprocess._generals import Project as Project
from targetprocess._generals import Release as Release
from targetprocess._generals import Team as Team
from targetprocess._generals import TeamIteration as TeamIteration
from targetprocess._generals import TestCase as TestCase
from targetprocess._joins import Assignment as Assignment
from targetprocess._joins import Relation as Relation
from targetprocess._joins import RoleEffort as RoleEffort
from targetprocess._joins import TeamAssignment as TeamAssignment
from targetprocess._joins import Time as Time
from targetprocess._lookups import CustomActivity as CustomActivity
from targetprocess._lookups import CustomRule as CustomRule
from targetprocess._lookups import EntityState as EntityState
from targetprocess._lookups import EntityType as EntityType
from targetprocess._lookups import Priority as Priority
from targetprocess._lookups import Process as Process
from targetprocess._lookups import RelationType as RelationType
from targetprocess._lookups import Role as Role
from targetprocess._lookups import Severity as Severity
from targetprocess._lookups import Term as Term
from targetprocess._lookups import User as User
from targetprocess._lookups import Workflow as Workflow
from targetprocess._nested import AssignedUsers as AssignedUsers
from targetprocess._nested import CustomFieldConfig as CustomFieldConfig
from targetprocess._nested import CustomFieldValue as CustomFieldValue
from targetprocess._nested import EntityRef as EntityRef
from targetprocess._nested import EntityTypeRef as EntityTypeRef
from targetprocess._nested import RefWithImportance as RefWithImportance
from targetprocess._nested import UserRef as UserRef

__all__ = [
    # Base classes
    "AssignableEntity",
    "Entity",
    "GeneralEntity",
    "NamedEntity",
    # Nested reference shapes
    "AssignedUsers",
    "CustomFieldConfig",
    "CustomFieldValue",
    "EntityRef",
    "EntityTypeRef",
    "RefWithImportance",
    "UserRef",
    # Assignable work items
    "Bug",
    "Epic",
    "Feature",
    "Request",
    "Task",
    "UserStory",
    # Other General types
    "Iteration",
    "Project",
    "Release",
    "Team",
    "TeamIteration",
    "TestCase",
    # Lookup, configuration and people types
    "CustomActivity",
    "CustomRule",
    "EntityState",
    "EntityType",
    "Priority",
    "Process",
    "RelationType",
    "Role",
    "Severity",
    "Term",
    "User",
    "Workflow",
    # Join entities
    "Assignment",
    "Relation",
    "RoleEffort",
    "TeamAssignment",
    "Time",
    # Attached content
    "Attachment",
    "Comment",
    "CustomField",
    "UploadedAttachment",
    "UploadedFileRef",
    # Date helpers
    "TPDateTime",
    "format_tp_date",
    "parse_tp_date",
]
