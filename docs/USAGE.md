# Usage guide

A task-oriented guide to `targetprocess-py`. For the full API contract see
[SPEC.md](../SPEC.md); for runnable scripts see [`examples/`](../examples/).

The library is **async-only** and built on `httpx`'s async client. Every code
block below uses the placeholder domain `example.tpondemand.com` — substitute
your own instance domain and supply credentials from the environment, never
hard-coded.

## Contents

- [Getting started](#getting-started)
- [Basic operations](#basic-operations)
- [Filtering and querying](#filtering-and-querying)
- [Pagination](#pagination)
- [Logging time](#logging-time)
- [Moving an item through its workflow](#moving-an-item-through-its-workflow)
- [Unscheduling an item](#unscheduling-an-item)
- [Relations](#relations)
- [Rich-text descriptions and comments](#rich-text-descriptions-and-comments)
- [Attachments](#attachments)
- [Error handling](#error-handling)
- [Async vs sync usage](#async-vs-sync-usage)
- [Safety-mode best practices](#safety-mode-best-practices)

## Getting started

Construct a `TargetProcessClient` with a domain, an authentication method, and
an explicit safety `mode`. `mode` is a required keyword argument with no
default, so every client declares its safety posture up front.

```python
import asyncio

from targetprocess_py import ClientMode, TargetProcessClient


async def main() -> None:
    async with TargetProcessClient(
        domain="example.tpondemand.com",
        token="your-api-token",  # sent as the access_token query parameter
        mode=ClientMode.READONLY,
    ) as client:
        story = await client.user_stories.get(id=123)
        print(story.id, story.name)


asyncio.run(main())
```

### Authentication

TargetProcess accepts a token **only** as an `access_token` query parameter —
there is no header-based token scheme — so the token travels in the request
URL. The alternative is HTTP Basic auth using real user credentials. A token
does not work as a Basic credential: TargetProcess answers
`Authorization: Basic <token>` with HTTP 401, so `basic_auth` takes a username
and password and a token always goes in `token=`. Provide exactly one;
supplying both or neither raises `ValueError` at construction.

```python
# Token (recommended): sent as ?access_token=...
TargetProcessClient(domain="example.tpondemand.com", token="…", mode=ClientMode.READONLY)

# Basic auth: sent as an Authorization: Basic header
TargetProcessClient(
    domain="example.tpondemand.com",
    basic_auth=("username", "password"),
    mode=ClientMode.READONLY,
)
```

Because the token is carried in the URL, it can appear in server and proxy
logs, and a copied request URL carries it too. Do not enable httpx request-URL
logging in production, and never copy or share a request URL that includes
`access_token`.

### Resolving the acting user

`users.logged_user()` returns the full `User` model for the user the client's
credential authenticates as, so a caller that needs its own user Id for
per-user queries need not carry it as configuration beside the token. The
result is cached for the client's lifetime, so a later call makes no request,
and it works on a `READONLY` client.

```python
async with TargetProcessClient(
    domain="example.tpondemand.com", token="…", mode=ClientMode.READONLY
) as client:
    user = await client.users.logged_user()
    print(user.id, user.login)
```

### Client lifecycle

Prefer `async with`, which closes the underlying HTTP client on exit. When you
cannot use a context manager, call `aclose()` explicitly so the connection pool
is not leaked:

```python
client = TargetProcessClient(
    domain="example.tpondemand.com", token="…", mode=ClientMode.READONLY
)
try:
    story = await client.user_stories.get(id=123)
finally:
    await client.aclose()
```

## Basic operations

Every typed resource manager (`client.user_stories`, `client.bugs`,
`client.tasks`, `client.features`, `client.epics`, `client.requests`,
`client.test_cases`, `client.times`, `client.releases`, `client.iterations`,
`client.projects`, `client.teams`, `client.users`, `client.entity_states`,
`client.priorities`, `client.comments`, `client.assignments`,
`client.team_assignments`, `client.role_efforts`, `client.roles`,
`client.attachments`, `client.relations`, `client.relation_types`,
`client.team_iterations`, `client.custom_fields`, `client.severities`,
`client.processes`, `client.workflows`, `client.entity_types`, `client.terms`,
`client.custom_activities`, `client.custom_rules`) exposes the same surface:

| Method | Signature | Mode |
| --- | --- | --- |
| `get` | `get(id, *, include=None, exclude=None, result_include=None, append=None, innertake=None) -> T` | any |
| `list` | `list(*, where=None, include=None, exclude=None, result_include=None, append=None, innertake=None, order_by=None, order_by_desc=None, skip=None, limit=None, page_size=25) -> AsyncIterator[T]` | any |
| `create` | `create(**fields) -> T` | READWRITE |
| `update` | `update(id, *, verify=False, **fields) -> T` | READWRITE |
| `delete` | `delete(id) -> None` | READWRITE |

```python
# Read a single entity
story = await client.user_stories.get(id=123)

# Iterate a collection (see Pagination below)
async for bug in client.bugs.list(limit=10):
    print(bug.id, bug.name)

# Create / update / delete require a READWRITE client
new_bug = await client.bugs.create(Name="Investigate outage", Project={"Id": 42})
await client.bugs.update(new_bug.id, Name="Investigate outage (triaged)")
await client.bugs.delete(new_bug.id)
```

Write fields use the API's PascalCase names (`Name`, `Project`, `Description`,
…); nested references are passed as `{"Id": <id>}`.

The server bounds the write surface as well as the client mode: each manager
declares what its collection's `/meta` reports, and an operation the server
refuses raises `ReadOnlyViolation` in every mode, before any request is sent.
`relation_types`, `entity_types` and `terms` are read-only on the server;
`custom_rules` accepts `update` (toggling `IsEnabled`) and refuses `create`
and `delete`. Every manager answers the question ahead of time -
`client.custom_rules.server_permits("create")` is `False`.

### Bulk writes

`create_many` / `update_many` send a whole batch as one
`POST /{collection}/bulk` request — one slot against the rate limiter instead
of one request per entity. `create_many` items must not carry an `Id` and
`update_many` items must (each raises `ValueError` otherwise — on the wire,
the presence of an `Id` alone decides create-vs-update). Like every mutation,
a bulk request is never auto-retried, and TargetProcess does not document
whether a failed bulk request is atomic — after an error, re-read rather than
assuming nothing was written.

```python
stories = await client.user_stories.create_many(
    [
        {"Name": "First story", "Project": {"Id": 42}},
        {"Name": "Second story", "Project": {"Id": 42}},
    ]
)
await client.user_stories.update_many(
    [{"Id": story.id, "Description": "Groomed"} for story in stories]
)
```

### Derived fields are not writable

Some fields TargetProcess reports are computed from records in another
collection rather than stored. A work item's `Effort`, `EffortCompleted` and
`EffortToDo` are the sums of the corresponding field over its `RoleEffort`
rows — one per role the process assigns effort to.

A direct write to one is answered with a success status either way, and the
response cannot tell you which of two things happened: TargetProcess stored the
value because the item has no `RoleEffort` rows to override it, or it recomputed
the field from those rows and your write changed nothing. The outcome depends on
the item's other records, not on the request. So `create`, `update`,
`create_many` and `update_many` refuse such a field before any request is sent —
on the typed work-item managers and on `client.entities` alike — with a
`ValueError` naming the route that does work:

```python
await client.user_stories.update(123, Effort=5)
# ValueError: Effort is not writable on UserStory: TargetProcess derives Effort
# from the entity's RoleEfforts, ... set the role's own row instead ...

# The route that does: find the (Assignable, Role) row and write it there.
async for row in client.role_efforts.list(
    where="Assignable.Id eq 123", include=["Role"]
):
    await client.role_efforts.update(row.id, Effort=5, verify=True)
```

Pass `allow_derived=True` to send the write anyway, when you know the item
carries no `RoleEffort` rows and you accept the outcome as TargetProcess gives
it. Only the three roll-ups above are refused; TargetProcess computes other
numbers too (`Progress`, `TimeSpent`, `TimeRemain`) and those are sent as
written.

### Verified writes

An update returns TargetProcess's own response to the write: its echo of the
entity, which can be stale. A caller who reads that echo can believe a change
landed when it did not. Pass `verify=True` and the library does not trust it:
after the write it re-reads each entity with one independent GET, narrowed to
the keys you sent, compares them, and returns the re-read model instead.
Because the re-read is narrowed, that model carries its `id` and
`resource_type` and the keys you sent: every other field on it is `None`, so
`get` the entity again when you need the rest.

```python
from targetprocess_py import VerificationError

try:
    story = await client.user_stories.update(
        123, NumericPriority=5, EntityState={"Id": 82}, verify=True
    )
    await client.tasks.update_many([{"Id": 456, "Name": "Groomed"}], verify=True)
except VerificationError as exc:
    for entity_id, fields in exc.mismatches.items():
        for field, (requested, observed) in fields.items():
            print(entity_id, field, requested, observed)
```

`update_many` re-reads every item after the whole batch and raises once, with
the failing entities in `exc.mismatches` and the rest in `exc.verified_ids`,
both keyed by integer Id. A verified batch names each entity once, by an
integer Id or a string of ASCII digits; a repeated or non-integer Id raises
`ValueError` before anything is sent. A verified write also raises `ValueError`
before anything is sent for a `CustomFields` entry that is not a mapping with a
string `Name`, since the re-read finds each entry by name. The comparison is on
the wire values:

- a reference such as `{"Id": 82}` matches on `Id` alone;
- `None` matches a null or a field the re-read does not carry;
- numbers compare numerically (`5` matches `5.0`), strings with surrounding
  whitespace stripped, and wire dates on the instant rather than the offset;
  a string never matches a number (`"3"` does not verify against `3`);
- any other field the re-read does not carry fails, observed as
  `VerificationError.ABSENT`.

A `Description` sent without the `<!--markdown-->` marker is stored
HTML-encoded (see [Rich-text descriptions and comments](#rich-text-descriptions-and-comments)),
so verifying it can fail on its own encoding. The generic `entities` accessor
does not take `verify`.

### Custom-field values

A custom-field value is written by the field's name, inside the entity's
`CustomFields` array. `set_custom_field` forms that payload on every typed
manager. Setting a value sends:

```json
{"CustomFields": [{"Name": "Release note", "Value": "Ships in October"}]}
```

and clearing one sends a null `Value`:

```json
{"CustomFields": [{"Name": "Release note", "Value": null}]}
```

```python
story = await client.user_stories.set_custom_field(123, "Release note", "Ships in October")
story = await client.user_stories.set_custom_field(123, "Release note", None)
```

Leaving a field out of an update is not a clear: TargetProcess keeps the old
value and still answers with a success status. So `set_custom_field` verifies
by default, re-reading `include=["CustomFields"]` and matching the entry by
name (case-insensitively); a cleared field may read back as `None`, `""`,
`False` or `0` - a CheckBox reads back `False`, and any of these empty
equivalents counts, regardless of the field's own configured type.
`VerificationError` here means the value did not land, a clear was discarded,
or no field of that name exists on the entity's process - a misspelt name, or
one configured on another process. Pass `verify=False` to skip the re-read.

The value is compared as sent, with no conversion between forms, so a string
value does not verify against a numeric field's number. A date-typed field
reads back in TargetProcess's `/Date(ms±HHMM)/` wire form, so it verifies
only when you send that form - `format_tp_date` of a timezone-aware `datetime`
(see [Time against a custom activity](time.md#time-against-a-custom-activity)) rather
than `"2026-10-01"` - or with `verify=False`. The verified return value is the
narrowed re-read: its `id`, `resource_type` and `custom_fields`, and no other
field.
Reading values back is `include=["CustomFields"]` on `get` or `list`.

### The generic `entities` accessor

For entity types without a typed manager (which ones, and why, is set out in
[SPEC.md](../SPEC.md) § *Typed versus generic coverage*), `client.entities`
takes the entity type name as its first argument and returns/yields
`NamedEntity` (so you still get `.name`, or `None` for types without a `Name`
field). It carries the full surface — `get`, `list`, `create`, `update`,
`delete`, `create_many`, `update_many` — with writes gated by the same
READWRITE check as the typed resources, and the same server-declared
refusals: a write naming `RelationType`, `EntityType` or `Term`, or a create
or delete naming `CustomRule`, is refused in every mode exactly as the typed
manager refuses it. The type name may be singular or plural — TargetProcess
accepts both (`"Milestone"` and `"Milestones"` both work).

```python
milestone = await client.entities.get("Milestone", 456)
async for build in client.entities.list("Builds", limit=5):
    print(build.id, build.name)

# Writes for uncovered collections (READWRITE client)
objective = await client.entities.create("Objective", Name="Q3 goal", Project={"Id": 42})
await client.entities.update("Objective", objective.id, Name="Q3 goal (revised)")
await client.entities.delete("Objective", objective.id)
```

### Finding the collections an instance exposes

`client.entity_types.list()` yields the instance's entity-type catalogue, which
is narrower than the set of collections the API routes. Lookup, join and
polymorphic-base collections such as `Roles`, `Relations`, `Assignments`,
`Assignables` and `Generals` are observed to answer on their own routes without
appearing in `/api/v1/EntityTypes`, so find out whether a collection exists by
requesting it:

```python
async for assignable in client.entities.list("Assignables", limit=1):
    print(assignable.resource_type, assignable.id)
```

## Filtering and querying

`where=` is a TargetProcess filter expression, passed through verbatim with no
client-side rewriting. `include=` names extra fields to hydrate on each entity
(rendered as `include=[Field1,Field2]`).

```python
# Open bugs, with their state and assignees hydrated
async for bug in client.bugs.list(
    where="(EntityState.IsFinal eq 'false')",
    include=["EntityState", "AssignedUser"],
):
    state = bug.entity_state.name if bug.entity_state else "—"
    print(f"{bug.id}: {bug.name} [{state}]")

# Compound filter
async for story in client.user_stories.list(
    where="(EntityState.Name eq 'In Progress') and (Effort gt 0)",
):
    print(story.id, story.name, story.effort)
```

Set membership takes parentheses, not brackets: `where="(Id in (123,456))"`.
The bracketed form, `(Id in [123,456])`, is refused with HTTP 400
(`RequestValidationError`) and a message that names neither the field nor the
offending token - although `include=` renders its list in brackets on the same
request.

Field access on returned models is snake_case (`bug.entity_state`,
`story.effort`). The six base `Entity`/`NamedEntity` fields (`Id`,
`ResourceType`, `CreateDate`, `ModifyDate`, `CustomFields`, `Name`)
additionally expose a PascalCase property matching the API; every other field
is snake_case-only.

Each model declares the full value and reference field surface TP's
`/api/v1/{collection}/meta` reports for its type, so the whole record is typed
rather than only a curated subset:

```python
story = await client.user_stories.get(id=123)

print(story.creator.full_name)      # UserRef - who raised it
print(story.priority.name)          # the entity-type-scoped Priority record
print(story.numeric_priority)       # the global ordering rank (a float), not a Priority
print(story.time_spent, story.effort_todo, story.forecast_end_date)
```

TP's **collection** properties (`Comments`, `Messages`, `Revisions`, …) stay
undeclared — they hydrate only via `include=` and arrive as an `Items`
envelope — so they remain reachable through `model_extra` under their wire
names. `CustomFields` and `AssignedUser` are the two exceptions and are
declared.

### Sorting and payload shaping

`list()` passes TP's remaining query parameters through as typed keyword
arguments:

- `order_by` / `order_by_desc` — server-side sort field, ascending /
  descending. Mutually exclusive: passing both raises `ValueError`.
- `exclude` — remove fields from each item (the complement of `include`).
- `result_include` — narrow each item to exactly the named fields, cutting
  payload size server-side.
- `append` — append calculated fields such as `"Tasks-Count"`.
- `innertake` — bound the size of nested collections hydrated via `include`.

`get()` accepts the same shaping parameters (`exclude`, `result_include`,
`append`, `innertake`); sorting applies only to `list()`.

```python
# The 10 most recently created open bugs, trimmed to Id and Name
async for bug in client.bugs.list(
    where="(EntityState.IsFinal eq 'false')",
    order_by_desc="CreateDate",
    result_include=["Id", "Name"],
    limit=10,
):
    print(bug.id, bug.name)
```

The library sends only v1 query parameters. Vendor examples written for the
v2 API narrow a payload with `select={…}`; v1 answers that with HTTP 200 and
returns the payload unchanged, so narrow a v1 response with `result_include`.
The 200 is TargetProcess's general answer to a query parameter it does not act
on: when trying a parameter against a raw URL, judge it by the change it makes
to the response, not by a 200 alone - a non-2xx answer is still a failed
request. Confirm a sort, for example, by comparing its ascending and
descending results.

### Resolving a priority

Priorities are scoped by entity type, so a name only identifies one record
once the entity type is known. Resolution succeeds only when exactly one
record matches: no match raises `NotFoundError` (listing the names that do
exist for that entity type), and several matches raise
`AmbiguousMatchError` rather than returning a guess.

```python
priority = await client.priorities.resolve("Must Have", entity_type="UserStory")
story = await client.user_stories.create(
    Name="Ship it", Project={"Id": 42}, Priority={"Id": priority.id}
)

# Or inspect the whole valid set for a type
for candidate in await client.priorities.for_entity_type("Bug"):
    print(candidate.id, candidate.name, candidate.importance)
```

Always pass the priority as an Id. TP returns HTTP 403 when a create request
carries a priority *name*, or an Id from another entity type's set.

### Resolving other lookups by name

The instance-wide lookups resolve the same way, without an entity type:
`roles`, `relation_types`, `severities`, `processes` and `entity_types` each
expose `resolve(name)`, case-insensitive, raising `NotFoundError` (listing
the names that exist) or `AmbiguousMatchError` rather than guessing. An
entity-type Id is what scopes the state, priority and custom-field
collections; a process Id scopes workflows and terms.
`custom_activities.resolve(name)` has the same contract but a narrower
promise: activities are scoped to a project and a user, so a name shared
across projects raises `AmbiguousMatchError` - narrow with
`client.custom_activities.list(where="Project.Id eq 42")` in that case.

```python
blocking = await client.severities.resolve("Blocking")
bug = await client.bugs.create(
    Name="Login fails", Project={"Id": 42}, Severity={"Id": blocking.id}
)

story_type = await client.entity_types.resolve("UserStory")
async for state in client.entity_states.list(where=f"EntityType.Id eq {story_type.id}"):
    print(state.name, state.is_final)

scrum = await client.processes.resolve("Scrum")
async for term in client.terms.list(where=f"Process.Id eq {scrum.id}"):
    print(term.word_key, "->", term.value)
```

Workflows and custom-field definitions are scoped by process *and* entity
type, so their names repeat and neither has a resolver — filter instead:
`client.workflows.list(where="(Process.Id eq 2) and (EntityType.Name eq 'Bug')")`.

### Resolving an entity state within its workflow

A state name identifies one state only inside one workflow: "Done" exists once
per workflow, and every process carries its own workflows. So a state resolves
against a workflow Id - from the `Workflow` reference of a state the item
already carries, or from filtering `workflows` as above - with the same
`NotFoundError`/`AmbiguousMatchError` contract as the lookups above.

```python
story = await client.user_stories.get(123, include=["EntityState"])
current = await client.entity_states.get(story.entity_state.id, include=["Workflow"])
workflow_id = current.workflow.id

done = await client.entity_states.resolve("Done", workflow_id=workflow_id)

# A workflow may have several final states - a completed and a rejected column
for state in await client.entity_states.final_states(workflow_id):
    print(state.id, state.name)

# Or every state of the workflow, each with its flags and Workflow reference
states = await client.entity_states.for_workflow(workflow_id)
```

## Pagination

`list()` returns an async iterator that fetches pages lazily as you consume it:

- `limit` — the maximum **total** number of items yielded across all pages
  (`None` = unbounded). `limit=0` yields nothing and makes no network request.
- `page_size` — the page size (`take=`) for each underlying request,
  independent of `limit`. The first request's `take` is `min(page_size, limit)`
  when `limit` is set.

```python
# At most 200 items, 50 per request
async for story in client.user_stories.list(limit=200, page_size=50):
    ...

# Collect into a list when you need one
stories = [s async for s in client.user_stories.list(limit=100)]
```

Pagination follows the server-provided `Next` URL verbatim, never a locally
recomputed `skip`, so short or irregular pages never silently drop or duplicate
items. Before each `Next` URL is followed it is checked against the client's
own host (scheme, host, port); a mismatched absolute `Next` raises
`NetworkError` rather than being followed — the client would otherwise leak the
`access_token` (carried on every request) to whatever host the response named.

### Offset paging with `skip` — opt-in

`skip` offsets where iteration starts, server-side. It is sent on the first
request only; from there pagination still follows the `Next` URL verbatim:

```python
# Items 51 onward
async for story in client.user_stories.list(skip=50):
    ...
```

The forward-only `Next` walk stays the default because it never recomputes
offsets — a short or irregular page cannot silently drop or duplicate items.
Paging manually with one `list(skip=...)` call per page reintroduces exactly
that hazard (items can shift between requests), so prefer a single iteration
with `limit` unless you genuinely need to start mid-collection.

## Logging time

Moved to [time.md](time.md): the `client.times` CRUD surface, the idempotent
`upsert` keyed on `(assignable, user, day)`, and time against a custom activity.

## Moving an item through its workflow

A work item carries two entity states: the project-workflow state on the item
itself, and the team-workflow state on its team assignment - the lane a team
board shows. Where the team has a workflow of its own the two move separately,
and writing only the item's `EntityState` leaves them split behind a success
status. `entity_state_levels` reads both levels, and `advance_state` moves them
as one transition.

```python
levels = await client.user_stories.entity_state_levels(123)
print(levels.project.state_id, levels.project.workflow_id)
print(levels.team, levels.team_assignment_id, levels.collapsed)  # team is None without one

if levels.team is None or levels.collapsed:
    # One write moves the item, and a collapsed team level with it
    moved = await client.user_stories.advance_state(123, to="Done")
else:
    # Choose each level's target from that level's own workflow
    project_final = await client.entity_states.final_states(levels.project.workflow_id)
    team_final = await client.entity_states.final_states(levels.team.workflow_id)
    moved = await client.user_stories.advance_state(
        123, to=project_final[0], team_to=team_final[0]
    )
```

A target is a state Id, a state name, or an `EntityState` read with its
`Workflow`, and each resolves within its own level's workflow (see
[Resolving an entity state within its workflow](#resolving-an-entity-state-within-its-workflow)).
With a distinct team level, leaving out `team_to` raises `SplitTransitionError`
before anything is written: pass the team level's target too. Where both levels
share one workflow `team_to` may be left out, and if given must name the same
state as `to`. An item with more than one team assignment raises
`AmbiguousMatchError`; move each through `client.team_assignments.update`.

`verify` defaults to `True`: each level is re-read as it is written - the item
after its write, then the team assignment after its own write (or, collapsed,
after the item's write moved it) - and a level not showing its target raises
`VerificationError`. An item write that did not apply therefore raises before
the team level is written, leaving both levels where they were, and the levels
returned are those re-reads. The two writes are not locked together, so a
failure after the item's write - the team write, or a re-read - leaves the item
moved and its team level not.

## Unscheduling an item

TargetProcess cascades a parent's `TeamIteration` onto its children, so an
explicit `null` on a child is answered with a success status whether the field
cleared, was discarded, or cleared and was immediately re-acquired from the
parent. `clear_team_iteration` sends the clear and then checks it, through the
same verified-write path as any other checked write - one write, one independent
re-read narrowed to the field - and raises `TeamIterationCascadeError` when the
field is still set:

```python
from targetprocess_py import TeamIterationCascadeError

try:
    story = await client.user_stories.clear_team_iteration(123)
    assert story.team_iteration is None
except TeamIterationCascadeError as exc:
    # The value the field was observed to hold, from the parent.
    print(exc.mismatches[123]["TeamIteration"])
```

The remedy is not a retry: unscheduling a child under a scheduled parent means
clearing or detaching the parent as well, or moving the item out from under it.
`TeamIterationCascadeError` is a `VerificationError`, so a caller already
handling "the re-read did not show the write" catches it too. The returned model
is the narrowed re-read, carrying `id`, `resource_type` and `team_iteration`
only. There is no `verify=False`: an unverified clear cannot be told from a
failed one, which is why this method exists — call `update(123,
TeamIteration=None)` directly if you want the write without the check.

## Relations

`client.relations` reads and writes `Relation` records directly: a
`RelationType` linking a `Master` to a `Slave`, where the Master is the source
of the dependency (see [SPEC.md](../SPEC.md#resources)). Relation-type Ids are
instance-specific, so resolve a type by name as under
[Resolving other lookups by name](#resolving-other-lookups-by-name).

Among relation types, `Blocker` and `Dependency` mean the Slave waits on the
Master, while `Relation`, `Link` and `Duplicate` associate two items without
either waiting. A check for whether anything still blocks an item counts only
the first two.

### Reading an item's inbound relations

An item's inbound relations - those naming it as the Slave - can be read in
the same request as the item, through two collections hydrated by `include=`.
Each hydrated collection is bounded separately by the server's inner-collection
size, so the example below reads every relation only while an item's relations
fit within that size; pass `innertake=` when an item can carry more:

```python
story = await client.user_stories.get(
    123,
    include=[
        "MasterRelations[Master,RelationType]",
        "InboundAssignables[Id,Name,EntityState[Name]]",
    ],
)
extra = story.model_extra or {}
state_by_id = {
    item["Id"]: item["EntityState"]["Name"]
    for item in extra["InboundAssignables"]["Items"]
}
for relation in extra["MasterRelations"]["Items"]:
    related_id = relation["Master"]["Id"]
    kind = relation["RelationType"]["Name"]
    print(kind, related_id, state_by_id.get(related_id))
```

Both arrive as `Items` envelopes in `model_extra`, like every collection
property. In `MasterRelations` each relation's `Master` is the related item and
its `Slave` the item that was read, with `RelationType` on the relation itself;
these are the wire names of the pair the `Relation` model also exposes as
`inbound` and `outbound`, which SPEC.md recommends for new code. `EntityState`
is observed not to expand under `Master`, a polymorphic reference, so the
related items' states come from `InboundAssignables` (the same items, where
they are assignables, with `EntityState` expanded), joined on `Id`. A `None`
from `state_by_id.get` means the related item was absent from
`InboundAssignables`.

Read the item through its typed collection rather than through `General`. The
`General` collection omits the fields only an `Assignable` carries, so
`client.entities.get("General", 123, include=["EntityState"])` is refused with
HTTP 400 (`RequestValidationError`) where
`client.user_stories.get(123, include=["EntityState"])` succeeds.

## Rich-text descriptions and comments

The library passes a `Description` - a work item's, or a comment's body - to
TargetProcess exactly as given, adding nothing. How TargetProcess stores it
depends on a marker, `<!--markdown-->`, at the very start of the text:

- **Marker at position 0**: the body is stored verbatim as Markdown, tables and
  fenced code blocks included. Read back through this library it arrives
  stripped of leading and trailing whitespace, like every string field, so a
  sync compares against the stripped text.
- **No marker**: the body goes through the HTML pipeline at storage time. Tags
  are preserved and text is entity-encoded, so `**bold**` is stored as
  `&#42;&#42;bold&#42;&#42;`.
- **Marker after leading whitespace**: not honoured. The marker is stripped
  and the body entity-encoded as HTML.

These rules are observed on comment bodies on user stories and requests, and
on a user story's `Description`, where a Markdown body carrying a table and a
fenced code block is stored unchanged. To write Markdown, prefix the marker
yourself:

```python
MARKDOWN = "<!--markdown-->"

await client.user_stories.update(
    123, Description=MARKDOWN + "## Scope\n\nThe export runs **nightly**."
)
await client.comments.create(
    General={"Id": 123}, Description=MARKDOWN + "Waiting on `review`."
)
```

## Attachments

`client.attachments` provides the usual CRUD surface over attachment
*records*, plus the two file-transfer helpers TargetProcess keeps outside its
JSON entity API: `download` fetches an attachment's bytes, and `upload` sends
a new file via the documented multipart endpoint (`POST /UploadFile.ashx`
with a `generalid` form field and the file as a `file` part).

```python
# The record names the file - but Uri, MimeType and Size are not in the
# default projection, so ask for them
attachment = await client.attachments.get(1234, include=["Uri", "MimeType", "Size"])
print(attachment.name, attachment.mime_type, attachment.size, attachment.uri)

# Fetch the bytes (works on a READONLY client)
content = await client.attachments.download(1234)

# Upload a new file onto an entity (requires READWRITE); the response is the
# created record, so there is no need to re-list the entity's attachments
uploaded = await client.attachments.upload(
    42, "screenshot.png", content, mime_type="image/png"
)
print(uploaded.id, uploaded.size, uploaded.uri)
```

Three things worth knowing, all TargetProcess's:

- **`Uri`, `MimeType` and `Size` need `include=`.** TargetProcess omits them
  from the projection a plain `get` or `list` returns, so the model reports
  them as `None` until they are asked for.
- **The upload response is camelCase**, unlike the rest of the API: a
  `{"items": [<attachment>]}` envelope carrying the created record, typed as
  `UploadedAttachment`. The shape is undocumented by the vendor and pinned by
  a recorded cassette rather than by a published contract, so a body that is
  not that envelope raises `ParseError`.
- **File endpoints are documented against Basic auth.** The vendor guide
  states a REST API token cannot download attached files. In practice a
  token-auth client uploads and downloads fine - the recorded integration
  suite exercises both - so the redirect the library refuses with `APIError`
  is a real failure, not the expected answer.

## Error handling

Every exception the library raises subclasses `TargetProcessError`, so you can
catch a specific failure or the base class. HTTP status codes map to types:

| Exception | Raised when |
| --- | --- |
| `AuthenticationError` | 401 — invalid or missing credentials |
| `ForbiddenError` | 403 — authenticated but not permitted |
| `NotFoundError` | 404 — no such entity |
| `RequestValidationError` | 400 — the request was rejected as invalid |
| `RateLimitError` | 429 — rate limited (including after retries are exhausted) |
| `APIError` | 5xx and any other error status; carries `status_code` and `details` |
| `NetworkError` | transport failure — no HTTP response arrived at all |
| `ParseError` | a response body failed Pydantic model validation |
| `ReadOnlyViolation` | a write was attempted on a `READONLY` client |
| `VerificationError` | a verified write (`verify=True`, or `set_custom_field` by default) read back an entity not showing a requested field; carries `mismatches` |
| `TeamIterationCascadeError` | a `VerificationError`: `clear_team_iteration` read the field back still set, TargetProcess having cascaded it from the parent |
| `SplitTransitionError` | `advance_state` would move one entity-state level without the other; carries `entity_id`, `project_workflow_id` and `team_workflow_id` |

```python
import logging

from targetprocess_py import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    TargetProcessError,
)

log = logging.getLogger(__name__)

try:
    story = await client.user_stories.get(id=123)
except NotFoundError:
    story = None
except AuthenticationError:
    raise  # credentials problem — not recoverable here
except RateLimitError:
    ...  # back off and retry later, or surface to the caller
except TargetProcessError as exc:
    log.warning("TargetProcess call failed: %s", exc)
    raise
```

### Retry and rate-limit behaviour

The request handler retries HTTP 429 and 5xx **only on safe methods**
(`get`/`list` — GET/HEAD/OPTIONS underneath): up to 3 retries (4 attempts
total) with exponential backoff (`0.5s * 2 ** attempt`, capped at 30s). A
`Retry-After` header is honoured when present (numeric seconds, or an HTTP-date
converted to a delay). Mutating methods (`create`/`update`/`delete`) are
**never** auto-retried — TargetProcess offers no idempotency guarantee for a
429'd mutation — so both 429 and 5xx surface immediately on writes; retrying a
mutation you know to be safe is the caller's own decision.

Every request (including retries) passes through an async rate limiter
(100 requests/minute) before being sent, so concurrent calls interleave rather
than serialising the event loop.

## Async vs sync usage

`targetprocess-py` is **async-only** by design — there is no synchronous
client, and a sync client is explicitly out of scope (see
[SPEC.md](../SPEC.md#purpose--scope)). Every resource method is a coroutine (or,
for `list`, an async generator) and must be awaited inside a running event
loop.

To call the library from otherwise-synchronous code, drive it with
`asyncio.run()` for a one-shot entry point:

```python
import asyncio

from targetprocess_py import ClientMode, TargetProcessClient


async def fetch_open_bugs() -> list[str]:
    async with TargetProcessClient(
        domain="example.tpondemand.com", token="…", mode=ClientMode.READONLY
    ) as client:
        return [
            f"{bug.id}: {bug.name}"
            async for bug in client.bugs.list(
                where="(EntityState.IsFinal eq 'false')", limit=20
            )
        ]


# Synchronous call site
lines = asyncio.run(fetch_open_bugs())
```

Do a single client's worth of work inside one `async with` block where you can:
opening a client per call is wasteful, and calling `asyncio.run()` repeatedly
spins up and tears down an event loop each time. Inside an already-running loop
(e.g. a web handler or another async framework) simply `await` the calls
directly — do not nest `asyncio.run()`.

## Safety-mode best practices

`TargetProcessClient` requires a `mode: ClientMode` — `READONLY` or
`READWRITE` — at construction. The value accepts the enum or its string form
(`"readonly"` / `"readwrite"`); an unrecognised value raises `ValueError`.

- **Default to `READONLY`** for reporting, analytics, dashboards, and any
  automation that only reads. A `READONLY` client raises `ReadOnlyViolation`
  the moment a write is attempted, so an accidental `create`/`update`/`delete`
  fails loudly instead of mutating production data.
- **Use `READWRITE` only where mutation is genuinely required**, and keep those
  code paths narrow and well-audited.
- **The mode is frozen after construction.** `__setattr__` rejects any later
  assignment to `mode` — build a new client to change posture rather than
  flipping an existing one.
- **Enforcement is two-layered.** Both the resource layer and the request
  handler check write permission, so a write is refused even if a caller
  bypasses the resource layer. (It is a best-effort guard against ordinary
  attribute assignment, not a hard sandbox.)

```python
from targetprocess_py import ClientMode, ReadOnlyViolation, TargetProcessClient

reporter = TargetProcessClient(
    domain="example.tpondemand.com", token="…", mode=ClientMode.READONLY
)
try:
    await reporter.bugs.create(Name="nope")
except ReadOnlyViolation:
    print("blocked — reporter is read-only")
```

See the [`examples/`](../examples/) directory for complete, runnable scripts:
`list_user_stories.py` and `readonly_reporting.py` (read-only) and
`create_bug.py` and `bulk_updates.py` (write, sandbox-only by construction).
