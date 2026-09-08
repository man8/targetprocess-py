"""Payloads captured verbatim from a live TargetProcess instance.

Hand-written fixtures test the shape a developer expects; these test the shape
TP actually sends, which is not always the same - a ``Bug``'s ``EntityType``
arrives with no ``Id``, a ``ResponsibleTeam`` with no ``Name``. Keeping them in
one module means the offline tests share one piece of evidence rather than each
inventing its own.

Captured from TP ``2608.2.0.3147`` on 2026-09-01, trimmed to the fields under
test. Ids and structural fields are as recorded; every name, login and free-text
value is a placeholder, as the cassette redaction policy requires.
"""

# UserStory 75380, hydrated with the whole declared field surface.
LIVE_USER_STORY: dict[str, object] = {
    "ResourceType": "UserStory",
    "Id": 75380,
    "Name": "Sample user story",
    "Tags": "Provider: Example, Country: XX",
    "NumericPriority": 63745.18191507797,
    "EntityVersion": 48630098,
    "IsNow": False,
    "IsNext": False,
    "IsPrevious": False,
    "Progress": 0.0,
    "TimeSpent": 0.5,
    "TimeRemain": 0.0,
    "InitialEstimate": 0.0,
    "Units": "h",
    "LeadTime": 0.37221218513194443,
    "CycleTime": 0.36834644446412035,
    "StartDate": "/Date(1788262495000+0200)/",
    "LastStateChangeDate": "/Date(1788262495000+0200)/",
    "CreateDate": "/Date(1788262161000+0200)/",
    "EntityType": {"ResourceType": "EntityType", "Id": 4, "Name": "UserStory"},
    "Creator": {
        "ResourceType": "GeneralUser",
        "Id": 342,
        "FirstName": "Alex",
        "LastName": "Example",
        "Login": "alex@example.com",
        "FullName": "Alex Example",
    },
    "Owner": {"ResourceType": "GeneralUser", "Id": 342, "FullName": "Alex Example"},
    "LastEditor": {"ResourceType": "GeneralUser", "Id": 342, "FullName": "Alex Example"},
    "Priority": {"ResourceType": "Priority", "Id": 5, "Name": "Nice To Have", "Importance": 5},
    "EntityState": {"ResourceType": "EntityState", "Id": 79, "Name": "Plan"},
    "Project": {"ResourceType": "Project", "Id": 33585, "Name": "Example Project"},
    "Team": {"ResourceType": "Team", "Id": 33091, "Name": "Example Team"},
    # TP sends this one with an Id and no Name at all.
    "ResponsibleTeam": {"ResourceType": "TeamAssignment", "Id": 82050},
}

# A Bug's EntityType, exactly as TP returns it: no Id, no Name. The UserStory
# above carries both, so the reference is not uniformly identified and cannot
# be modelled by a shape that requires an Id.
LIVE_BUG_PARTIAL_ENTITY_TYPE: dict[str, object] = {
    "ResourceType": "Bug",
    "Id": 74436,
    "Name": "Sample bug",
    "EntityType": {"ResourceType": "EntityType", "IsUnitInHourOnly": False},
    "Severity": {"ResourceType": "Severity", "Id": 5, "Name": "Enhancement", "Importance": 5},
    "Priority": {"ResourceType": "Priority", "Id": 7, "Name": "Fix If Time", "Importance": 2},
}

# The same omission on a Task, where IsUnitInHourOnly is the only key besides
# ResourceType.
LIVE_TASK_PARTIAL_ENTITY_TYPE: dict[str, object] = {
    "ResourceType": "Task",
    "Id": 5100,
    "Name": "Write the migration",
    "EntityType": {"ResourceType": "EntityType", "IsUnitInHourOnly": True},
    "Parent": {"ResourceType": "Assignable", "Id": 5099, "Name": "Parent story"},
}

# Keys no model declares, so each must survive in model_extra. Two kinds, both
# real failure modes: a TP collection property (declared by the API but
# hydrated only via include=, and never a model field), and a key this version
# of the library has never heard of.
UNDECLARED_KEYS: dict[str, object] = {
    "Messages": {"Items": []},
    "Revisions": {"Items": []},
    "SomeFutureField": "kept",
}
