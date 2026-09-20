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

from targetprocess_py._assignables import Bug as Bug
from targetprocess_py._assignables import Epic as Epic
from targetprocess_py._assignables import Feature as Feature
from targetprocess_py._assignables import Request as Request
from targetprocess_py._assignables import Task as Task
from targetprocess_py._assignables import UserStory as UserStory
from targetprocess_py._base import AssignableEntity as AssignableEntity
from targetprocess_py._base import Entity as Entity
from targetprocess_py._base import GeneralEntity as GeneralEntity
from targetprocess_py._base import NamedEntity as NamedEntity
from targetprocess_py._content import Attachment as Attachment
from targetprocess_py._content import Comment as Comment
from targetprocess_py._content import CustomField as CustomField
from targetprocess_py._content import UploadedAttachment as UploadedAttachment
from targetprocess_py._content import UploadedFileRef as UploadedFileRef
from targetprocess_py._dates import TPDateTime as TPDateTime
from targetprocess_py._dates import format_tp_date as format_tp_date
from targetprocess_py._dates import parse_tp_date as parse_tp_date
from targetprocess_py._generals import Iteration as Iteration
from targetprocess_py._generals import Project as Project
from targetprocess_py._generals import Release as Release
from targetprocess_py._generals import Team as Team
from targetprocess_py._generals import TeamIteration as TeamIteration
from targetprocess_py._generals import TestCase as TestCase
from targetprocess_py._joins import Assignment as Assignment
from targetprocess_py._joins import Relation as Relation
from targetprocess_py._joins import RoleEffort as RoleEffort
from targetprocess_py._joins import TeamAssignment as TeamAssignment
from targetprocess_py._joins import Time as Time
from targetprocess_py._lookups import CustomActivity as CustomActivity
from targetprocess_py._lookups import CustomRule as CustomRule
from targetprocess_py._lookups import EntityState as EntityState
from targetprocess_py._lookups import EntityType as EntityType
from targetprocess_py._lookups import Priority as Priority
from targetprocess_py._lookups import Process as Process
from targetprocess_py._lookups import RelationType as RelationType
from targetprocess_py._lookups import Role as Role
from targetprocess_py._lookups import Severity as Severity
from targetprocess_py._lookups import Term as Term
from targetprocess_py._lookups import User as User
from targetprocess_py._lookups import Workflow as Workflow
from targetprocess_py._nested import AssignedUsers as AssignedUsers
from targetprocess_py._nested import CustomFieldConfig as CustomFieldConfig
from targetprocess_py._nested import CustomFieldValue as CustomFieldValue
from targetprocess_py._nested import EntityRef as EntityRef
from targetprocess_py._nested import EntityTypeRef as EntityTypeRef
from targetprocess_py._nested import RefWithImportance as RefWithImportance
from targetprocess_py._nested import UserRef as UserRef

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
