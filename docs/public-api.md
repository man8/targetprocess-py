# Public API surface

The library's public surface: client construction, the acting user, the
resource managers and what each adds to the shared read/write methods, the
models, and the exception hierarchy. Split out of [SPEC.md](../SPEC.md), which
carries the behavioural contract itself and links here.

### Client construction

```python
TargetProcessClient(
    domain: str,
    *,
    mode: ClientMode,             # required - no default
    token: str | None = None,
    basic_auth: tuple[str, str] | None = None,
    timeout: float = 30.0,
)
```

`mode` is a required keyword with no default, so every client is
constructed with an explicit safety posture. Exactly one of `token` /
`basic_auth` must be provided; supplying neither `token` nor `basic_auth`,
or supplying both, raises `ValueError` at the transport layer.

### Acting user

`users.logged_user() -> User` returns the user the credential authenticates as
from one `GET /api/v1/Users/LoggedUser`, parsed as `users.get` parses a record
(the same `ParseError`). It is cached on the client's one `users` resource, so
a second call makes no request; a failure caches nothing, there is no lock,
and it works on a `READONLY` client.

### Resources

Typed resource managers, each exposed as a property on the client:
`user_stories`, `bugs`, `tasks`, `features`, `epics`, `requests`,
`test_cases`, `times`, `releases`, `iterations`, `projects`, `teams`, `users`,
`entity_states`, `priorities`, `comments`, `assignments`, `team_assignments`,
`role_efforts`, `roles`, `attachments`, `relations`, `relation_types`,
`team_iterations`, `custom_fields`, `severities`, `processes`, `workflows`,
`entity_types`, `terms`, `custom_activities`, `custom_rules`. Each supports:

- `get(id, *, include=None, exclude=None, result_include=None, append=None,
  innertake=None) -> T`
- `list(*, where=None, include=None, exclude=None, result_include=None,
  append=None, innertake=None, order_by=None, order_by_desc=None, skip=None,
  limit=None, page_size=25) -> AsyncIterator[T]`
- `create(*, allow_derived=False, **fields) -> T` (READWRITE only)
- `update(id, *, verify=False, allow_derived=False, **fields) -> T` (READWRITE only)
- `delete(id) -> None` (READWRITE only)
- `create_many(items, *, allow_derived=False) -> list[T]` /
  `update_many(items, *, verify=False, allow_derived=False) -> list[T]`
  (READWRITE only) - one bulk request for the whole batch; see
  [SPEC.md § Bulk write semantics](../SPEC.md#bulk-write-semantics). On a
  collection the server restricts (next paragraph) they raise
  `ReadOnlyViolation` in every mode, as the single-item writes do

The write surface is bounded by what the server accepts as well as by the
client mode. Each collection's `/api/v1/{collection}/meta` reports
`CanCreate` / `CanUpdate` / `CanDelete`, and a typed manager declares that
surface on its class - `BaseResource.server_read_only` for the all-false
case, or the per-operation `server_can_create` / `server_can_update` /
`server_can_delete`; `server_permits(operation)` reads them. An operation the
server refuses raises `ReadOnlyViolation` in every mode - READWRITE included
- before any request is sent, on the single-item and bulk methods alike.
Three collections are read-only outright: `relation_types`, `entity_types`
and `terms`. One is partial: `custom_rules` accepts `update` / `update_many`
(toggling `IsEnabled`, the one settable field) and refuses `create`,
`create_many` and `delete`. Every other typed collection is fully writable.
The flags are read from `/meta`, never established by probing a write.

A write is bounded at the field level too: `BaseResource.derived_fields` names the
fields TP computes from another collection, which the four write methods refuse
with `ValueError` unless the call passes `allow_derived=True` - see
[SPEC.md § Derived-field writes](../SPEC.md#derived-field-writes).

`times` additionally provides `find_for_day` and `upsert` - see
[SPEC.md § Time upsert semantics](../SPEC.md#time-upsert-semantics).

`priorities` additionally exposes the entity-type-scoped lookups that make a
priority name resolvable: `for_entity_type(entity_type) -> list[Priority]`
returns the valid set, and `resolve(name, *, entity_type) -> Priority` returns
the single match — raising `NotFoundError` when nothing matches (listing the
names that do) and `AmbiguousMatchError` when several do, so a caller never
receives a guessed Id.

`entity_states` additionally exposes the workflow-scoped lookups, since a state
name repeats once per workflow and a workflow once per process:
`for_workflow(workflow_id) -> list[EntityState]` returns one workflow's states
(`where=Workflow.Id eq …`), `resolve(name, *, workflow_id) -> EntityState`
returns the single match with the same semantics as `priorities.resolve`, and
`final_states(workflow_id) -> list[EntityState]` returns those whose `IsFinal`
is true, in API order (a workflow may have several).

`assignments` is the read/write surface for who is assigned to a work item
in which role (an `Assignment` pairs a `GeneralUser` with a `Role` on an
`Assignable`; `Owner` only records who created the item). `roles`
additionally exposes `resolve(name) -> Role` — the lookup that makes
assignment payloads constructible — with the same
`NotFoundError`/`AmbiguousMatchError` semantics as `priorities.resolve`
(roles are instance-wide, so it takes no `entity_type`).

`attachments` covers the attachment *record* through the usual CRUD surface
and adds the two file-transfer operations TP keeps outside its JSON entity
API. The `Attachment` model declares `Uri`, `MimeType`, `Size` and
`ThumbnailUri`, but TP leaves all four out of the projection it returns by
default, so a plain `get` reports them as `None` and a caller that needs them
asks by `include=`.

`download(id) -> bytes` GETs the instance-root path
`/Attachment.aspx?AttachmentID=<id>` — the same path a fetched record carries
in `uri`. `upload(general_id, filename, content, *, mime_type=None) ->
UploadedAttachment` POSTs `multipart/form-data` to the instance-root
`/UploadFile.ashx` with a `generalid` form field and the file as a `file`
part — the vendor-documented upload wire shape, which differs from the
ordinary JSON entity POST.

TP documents that request but not its response. What the endpoint sends,
recorded in the write-path integration suite, is a **camelCase**
`{"items": [<attachment>]}` envelope holding the created record: the same
attachment the entity API serves, plus `persistedMimeType` and
`persistedSize` alongside their entity-API equivalents, and a `date` in
ISO-8601 rather than TP's `/Date(ms±HHMM)/` wire format. `UploadedAttachment`
types it, so an upload returns the record it created and a caller need not
re-list the entity's attachments to find it. A body that is not that envelope
raises `ParseError` rather than being handed back unread — the shape is
undocumented and therefore unguaranteed, and a caller cannot tell an unparsed
body from a failed upload.

Both helpers refuse a 3xx response with `APIError` rather than following it:
the credential must not travel to a server-chosen host, and a redirected file
operation transferred nothing, which must not read as an empty download or a
successful upload. TP documents its file endpoints against Basic auth and the
vendor guide states that a REST API token cannot download an attached file;
the recorded run contradicts that — an upload and a download of the uploaded
bytes both succeed under token auth — so a redirect here is a real failure to
surface rather than the expected outcome. `upload` is write-gated at both
layers exactly like every other mutation; `download` is a read and works on a
`READONLY` client.

`relations` is the read/write surface for entity-to-entity relationships (a
`Relation` links a `Master` entity to a `Slave` entity, typed by a
`RelationType` — the Master is the source of the dependency, so in a Blocker
relation the Master is the blocking item and the Slave the blocked one).
`relation_types` additionally exposes `resolve(name) -> RelationType` — the
lookup that makes relation payloads constructible, since RelationType Ids are
instance-specific — with the same `NotFoundError`/`AmbiguousMatchError`
semantics as `roles.resolve` (relation types are instance-wide, so it takes
no `entity_type`). TP declares the RelationTypes collection itself read-only,
and the client enforces that: `create`, `update` and `delete` on
`relation_types` raise `ReadOnlyViolation` in every mode — READWRITE
included — before any request is sent.

`team_iterations` covers the team-owned sprint (`TeamIteration`): a sprint is
found by team (`where="Team.Id eq 51"`), and `IsCurrent` marks the one in
progress. `custom_fields` covers custom-field *definitions* - the
`CustomField` record configured on a process for one entity type - as
distinct from the per-entity values every model carries in `custom_fields`;
definitions are scoped by process and entity type, so they are filtered
rather than resolved.

The configuration lookups: `severities` (Bug severities, instance-wide, with
`resolve(name) -> Severity`), `processes` (with `resolve(name) -> Process`; a
process Id is what scopes workflows, custom-field definitions and terms),
`workflows` (scoped to a process and an entity type; names repeat across
processes, so there is no resolver - filter instead), `entity_types` (the
instance's own type catalogue, read-only, with `resolve(name) -> EntityType`),
`terms` (a process's display word for an entity type, read-only; a `Term`
carries no `Name`), `custom_activities` (the non-work-item target for `Time`,
project- and user-scoped, with `resolve(name) -> CustomActivity`) and
`custom_rules` (update-only, as above). Every `resolve` shares one contract
with `roles.resolve`: case-insensitive, `NotFoundError` listing the names
that do exist, `AmbiguousMatchError` on several matches, never a guessed Id.

`entities` is the generic escape hatch for any entity type known only at
runtime; it takes an explicit `entity_type` as its first positional
argument on every method (`client.entities.get("Bug", 789)`,
`client.entities.list("Comments", limit=2)`) and always returns/yields
`NamedEntity` rather than a specific subclass, so callers get `.name` (or
`None`, for entity types with no `Name` field) without needing to know the
concrete type ahead of time. It is a full write surface too:
`create(entity_type, **fields)`, `update(entity_type, id, **fields)`,
`delete(entity_type, id)`, `create_many(entity_type, items)` and
`update_many(entity_type, items)` give every collection with no typed
manager a usable (if untyped) write path. This is a deliberate stance, not
an accident of coverage: a typed manager adds models and conveniences,
never exclusive write access. Generic writes run through the same
`ClientMode.READWRITE` gate as the typed resources, and the typed layer's
server-side capability guard is mirrored by entity-type name: a write naming
a collection TP itself restricts - `RelationType`, `EntityType` and `Term`
for every write, `CustomRule` for create and delete; any casing, singular or
plural - raises `ReadOnlyViolation` in every mode, exactly as the typed
manager does, so the generic path cannot be used to sidestep that guard. The
mirror is a map from every spelling TP accepts for the collection (the
singular entity type and its plural - `Processes`, `Severities` - in any
casing) to the typed resource class, and a test walks every exported
resource to fail if one with a restriction is missing from it or unreachable
under either spelling.

#### Typed versus generic coverage

A live instance exposes 64 v1 collections; 32 have a typed manager. The
split is a stance, not a backlog. The typed set is the work-item types, the
planning and organisational types, the join and content types that carry the
common write paths (comments, assignments, relations, attachments, time), and
the lookup and configuration collections a client needs to resolve names to
Ids and to discover the instance's own configuration. The rest stays on
`entities` by design: the work-item types not modelled (Impediments,
Milestones, Builds, Programs, PortfolioEpics, Risks, RiskActions, Rates and
the TestPlan / TestStep family), the polymorphic bases (Assignables,
Generals, InboundAssignables, OutboundAssignables), the people and allocation
collections (Requesters, Companies, GeneralUsers, ProjectMembers, the
allocation join types, GeneralFollowers) and the metadata and audit
collections (EntityStateHistory, Revisions, RevisionFiles, Messages,
MessageUids, Tags). `entities` reads and writes every one of them under the
same mode gate, so nothing is unreachable. A typed manager for one of them
follows demand rather than completeness, and arrives with its model, its
`/meta`-derived write surface and its own tests.

An `entity_type` must be a plain TP identifier - letters, digits and
underscores, starting with a letter - the same rule
`priorities.for_entity_type` applies to its filter. The name is
interpolated straight into the request path, and on the generic surface it
is caller-supplied at runtime (often echoing a server-returned
`ResourceType`), so anything else - a path segment (`"UserStories/57731"`
would turn a create into an update of that entity), a trailing slash, a
query string, whitespace - raises `ValueError` before any request is sent.
`RequestHandler` enforces this on every entity method, reads included, and
`entities` re-checks it ahead of its read-only-collection lookup, so a
perturbed spelling is refused as malformed rather than slipping past the
name match.

### Models

#### Class hierarchy

The model hierarchy mirrors TP's own, which `/meta` declares: most domain types
derive from `General`, and the work-item types derive from `Assignable`, itself
a `General`. Modelling those two bases means every field TP defines once is
declared once.

- `Entity` - base fields `id`/`Id`, `resource_type`/`ResourceType`,
  `create_date`/`CreateDate`, `modify_date`/`ModifyDate`,
  `custom_fields`/`CustomFields`, each accessible via snake_case or a
  PascalCase property matching the API.
- `NamedEntity(Entity)` - adds `name`/`Name`, with the same property pair.
- `GeneralEntity(NamedEntity)` - TP's `General`: `description`, `tags`,
  `start_date`, `end_date`, `last_comment_date`, `numeric_priority`,
  `entity_version`, `is_now`/`is_next`/`is_previous`, and the references
  `entity_type`, `owner`, `creator`, `last_editor`, `last_commented_user`,
  `project`, `linked_test_plan`, `milestone`.
- `AssignableEntity(GeneralEntity)` - TP's `Assignable`, adding the effort and
  flow surface (`effort`, `effort_completed`, `effort_todo`, `progress`,
  `time_spent`, `time_remain`, `units`, `lead_time`, `cycle_time`), the date
  fields (`last_state_change_date`, `planned_start_date`, `planned_end_date`,
  `forecast_end_date`), the references (`entity_state`, `priority`, `release`,
  `iteration`, `team_iteration`, `team`, `responsible_team`), and
  `assigned_user`.

`UserStory`, `Bug`, `Task`, `Feature`, `Epic` and `Request` extend
`AssignableEntity`. `Project`, `Team`, `Release`, `Iteration`, `TeamIteration`
and `TestCase` extend `GeneralEntity`. The types TP defines outside that
hierarchy - `User`, the lookup and configuration types (`EntityState`,
`Priority`, `Role`, `RelationType`, `Severity`, `Process`, `Workflow`,
`EntityType`, `Term`, `CustomActivity`, `CustomRule`) and the join and content
types (`Assignment`, `TeamAssignment`, `RoleEffort`, `Relation`, `Time`,
`Comment`, `Attachment`, `CustomField`) - extend `Entity` or `NamedEntity`
directly, by whether they carry a `Name` (`Term` is the one lookup that does
not: it is keyed by `WordKey`).

Only the six `Entity`/`NamedEntity` fields listed above expose a PascalCase
property accessor; every other field - including those on `GeneralEntity` and
`AssignableEntity`, and type-specific ones like `Bug.severity` or
`Request.votes_count` - is snake_case-only.

`create_date`/`modify_date`/`custom_fields` sit on `Entity` and so exist on
every model, but TP exposes none of the three on every type; where a type's
`/meta` omits them they simply stay `None`.

#### Field coverage

Each model declares every **value** and **reference** property its type's
`/api/v1/{collection}/meta` names - measured at 656 of 656 across the 32
modelled types against TP `2608.2.0.3147`.

One field is deliberately excluded, and counted out of that denominator rather
than left to read as a gap: `User.Password`, which TP marks unreadable
(`CanGet: false`), so declaring it would put a password-shaped attribute into
every `model_dump`. The guarantee is about what TP returns: a read payload
never carries the field, so neither does a dump of one. It can still be
supplied through
`users.update(id, Password=...)`, which passes fields through verbatim.

**Collection** properties (`Comments`, `Messages`, `Assignments`, `Revisions`,
`Followers`, ...) are outside that count and remain undeclared. They are
hydrated only via `include=` and arrive as an `Items` envelope rather than as a
field of the entity, so they land in `model_extra` under their wire names. The
two exceptions are `CustomFields`, declared on `Entity`, and `AssignedUser`,
declared on `AssignableEntity`.

One wire name collides with that first exception: on a `Process`,
`CustomFields` is the collection of custom-field *definitions* (an `Items`
envelope of `CustomField` records), not the values array `Entity.custom_fields`
holds. A default Process payload carries no such key, so plain reads parse;
`processes.get` / `processes.list` - and the same collection through
`entities` - refuse `include=["CustomFields"]` with `ValueError` before any
request is sent (`BaseResource.unhydratable_includes`, checked by
`check_include`; the nested form `CustomFields[...]` and any casing are caught
too), rather than failing the parse afterwards. The definitions are listed
through `custom_fields` filtered by `Process.Id`. The coverage script reads
the same declaration into its `UNHYDRATABLE` map and leaves the field out of
`--validate`, with the same staleness check as its other maps.

`scripts/check_model_coverage.py` measures this against a live instance and
regenerates the table (`--markdown`). It is dev-time only and not CI-gated: it
needs a real token, which CI does not have. `tests/test_model_field_coverage.py`
is its offline counterpart, pinning the surface against captured payloads.

A handful of fields are declared that this instance's `/meta` does not list.
Each is recorded in the script's `KNOWN_DEVIATIONS`, so a genuinely new
mismatch is the only thing a run surfaces: `Task.Parent` (undocumented but
queryable, returning the owning `Assignable`), and `Feature.BusinessValue`,
`Epic.BusinessValue`, `Iteration.Team`, `TestCase.EntityState` and
`TestCase.AssignedUser`, none of which exist on the measured instance -
`include=` returns HTTP 400 for those five - but which stay declared because
removing a published field would break callers.

#### Extra-field policy

Entity models set `extra="allow"`: an undeclared API field is never silently
discarded. TP payload shapes vary by instance and version, so undeclared keys
are tolerated rather than rejected (`extra="forbid"` would break on benign
variance), but they are preserved - kept in `model_extra` under their wire
(PascalCase) names, reachable via attribute access (`us.Messages` - dynamic, so
under a strict type checker use the typed `model_extra[...]` path), and
included in `model_dump` output. What reaches `model_extra` in practice is a
collection property, an instance-specific field, or a field added by a TP
version newer than the models. The nested
reference models (`EntityRef`, `EntityTypeRef`, `UserRef`, `RefWithImportance`)
and
`CustomFieldValue` / `CustomFieldConfig` are deliberately lean curated
projections and keep Pydantic's default `extra="ignore"` - extras there
duplicate what the parent entity or a direct fetch of the referenced entity
already carries.

The same policy governs writes: with `extra="allow"` plus
`validate_assignment`, assigning an undeclared attribute (a mistyped field
name included) is not an error - the value lands in `model_extra` and
appears in dumps. This is the accepted cost of preserving unknown wire
fields; declared fields still validate on assignment as before.

#### Round-trip fidelity

`model_dump(by_alias=True)` **preserves every top-level key** of a live
payload: declared fields under their wire alias and undeclared ones from
`model_extra`. The guarantee stops at the entity's own keys — a nested
reference keeps only what its reference model declares (second bullet
below). Declared *values* are normalised to their declared type rather than
echoed verbatim, so a dump is not byte-identical to the wire payload:

- A date becomes a timezone-aware `datetime`, not the `/Date(ms±HHMM)/` string.
  `format_tp_date` converts back.
- A nested reference is projected onto its model's fields, so a key the
  reference model does not declare is dropped (`EntityRef` has no
  `ResourceType`) and one it declares but the payload omitted appears as
  `None`.
- `str_strip_whitespace=True` means a padded string is stored and dumped
  stripped. This matters on read-modify-write: compare against the stripped
  value or a padded field updates on every run instead of converging (the
  hazard `times.upsert` already documents for `description`).

Writes are unaffected: the resource layer takes `**fields` and never dumps an
entity back to TP.

#### Numeric range constraints

Fields TP computes and returns carry no `ge`/`le` bound. A constraint on a
server-supplied value fails the **whole entity** rather than the field, so one
out-of-range roll-up would abort an entire `list()` page with a `ParseError` -
and TP documents no bounds on effort, progress or flow metrics to assert. The
`RoleEffort` and `Time` join models carry none either; `times.upsert` validates
on the write side, where the value originates and a range error is actionable.
The attached-content byte-size fields still carry `ge=0`.

`custom_fields` (`CustomFields`) sits on the `Entity` base, so custom-field
values are reachable on every entity type: fetched with
`include=[CustomFields]`, the payload's `CustomFields` array parses into a
`list[CustomFieldValue] | None` rather than landing raw in `model_extra`.
Every typed manager writes one with
`set_custom_field(id, name, value, *, verify=True) -> T`, which sends
`{"CustomFields": [{"Name": name, "Value": value}]}` through `update`; a null
`Value` clears. A partial update omitting a custom field keeps its value behind
a success status, so `verify` defaults on here (off on `update`): the re-read
matches the entry by name, a clear reading back any of TP's empty-equivalent
values - null, `""`, `False` or `0`, since a CheckBox reads back `False` and a
numeric field `0` - and raises `VerificationError` when the value differs or no
entry of that name comes back. A date-typed value reads back in wire form, so it
verifies only when sent in that form (`format_tp_date`) or with `verify=False`.

Nested references use one of four lightweight shapes, chosen by what the
API actually sends:

- `EntityRef` - the common `{Id, Name}` shape (Project, Team, EntityState, ...).
  `Name` is optional: TP sends `ResponsibleTeam` as `{ResourceType, Id}` alone.
- `UserRef` - the User-shaped `{ResourceType, Id, FirstName, LastName, Login,
  FullName}` reference used by Owner/Creator/LastEditor/LastCommentedUser/
  AssignedUser-style fields (notably no `Name` key).
- `RefWithImportance` - `{ResourceType, Id, Name, Importance}`, used by
  `Bug.severity` and by the `priority` field every assignable carries.
- `EntityTypeRef` - the `EntityType` reference, whose `Id` **and** `Name` are
  both optional. TP does not identify this one uniformly: a `UserStory` carries
  `{ResourceType, Id, Name, IsUnitInHourOnly}`, a `Bug` or `Task` only
  `{ResourceType, IsUnitInHourOnly}`. `EntityRef`, whose `Id` is required,
  cannot model it - a required `Id` would fail every Bug and every Task on a
  nested field TP chose not to populate. Read the entity's own `resource_type`,
  always present, when the question is what kind of thing a record is.

Two fields read as a priority and are not interchangeable: `priority` is the
entity-type-scoped `Priority` record, arriving with an `Importance`, while
`numeric_priority` on `GeneralEntity` is TP's continuous backlog-ordering rank.

`CustomField.Config` is a reference in `/meta` but not an entity reference - it
arrives as a settings object with no `Id`, so `EntityRef` cannot model it.
`CustomFieldConfig` covers it (`default_value`, `calculation_model`, `units`,
`format_specifier`, ...).

`Priority` extends `NamedEntity` with `importance`, `is_default`,
`is_most_important` and an `entity_type` `EntityRef` naming the entity type
whose set it belongs to.

`Relation` extends `Entity` with `relation_type` and two reference pairs that
name the same two records: `inbound`/`outbound` (current) and `master`/`slave`
(marked deprecated in `/meta`). `inbound` mirrors `master` and `outbound`
mirrors `slave`; prefer the former pair in new code. `RelationType` is a bare
`NamedEntity` lookup (the API declares only `Id` and `Name`).

`Time` declares `assignable` plus the narrower back-reference TP exposes per
work-item type (`user_story`, `task`, `bug`, `request`, `test_plan`,
`test_plan_run`, `custom_activity`), of which exactly one is populated for a
given entry - a `CustomActivity` entry has no `assignable` at all, so the
back-reference is the only record of what the time was logged against.

Assignment-style collections (e.g. `AssignedUser` fetched via `include=`)
arrive wrapped as `{"Items": [...]}` rather than a bare list; the
`AssignedUsers` type unwraps this automatically.

### Exceptions

All library exceptions extend `TargetProcessError`:

- `APIError` - any error response not covered by a more specific exception
  below (mainly 5xx); carries `status_code` and `details`.
- `AuthenticationError` - 401.
- `ForbiddenError` - 403.
- `NotFoundError` - 404.
- `RequestValidationError` - 400.
- `RateLimitError` - 429 (including after retries are exhausted).
- `NetworkError` - transport-level failure (connection error, timeout, DNS
  failure, ...); no HTTP response was received at all.
- `ParseError` - a response body failed Pydantic model validation.
- `ReadOnlyViolation` - a write was attempted on a READONLY client, or - in
  any mode - an operation TP itself declares a collection incapable of
  (`relation_types`, `entity_types` and `terms` for every write,
  `custom_rules` for create and delete, or the same collections addressed
  through the generic `entities` surface); either way the write is refused
  before any request is sent.
- `AmbiguousMatchError` - a key or lookup that must identify at most one
  record matched several (raised by the name resolvers `priorities.resolve`,
  `roles.resolve`, `relation_types.resolve`, `severities.resolve`,
  `processes.resolve`, `entity_types.resolve` and
  `custom_activities.resolve`, and by `times.upsert`);
  optionally carries `assignable_id`, `user_id`, `day`, and `count` where the
  caller has that context.
- `VerificationError` - an update with `verify=True` read back an entity not
  showing a requested field; carries `mismatches` and `verified_ids`.
- `TeamIterationCascadeError` - a `VerificationError`: `clear_team_iteration`
  read the `TeamIteration` back still set. A defensive guard for a discard of
  the explicit `null` that was reported but never reproduced; the observed
  value is in `mismatches`.
- `SplitTransitionError` - `advance_state` would move one entity-state level
  without the other; carries `entity_id` and both workflow Ids.
