# targetprocess-py

## Purpose & Scope

An async Python library for the TargetProcess v1 REST API. It provides a
typed, safety-conscious client: typed resource managers for the common
entity types, a generic fallback for any other entity type, Pydantic models
with both snake_case and PascalCase field access, and an immutable
readonly/readwrite safety mode enforced at two layers.

The library is async-only (built on `httpx`'s async client) - there is no
sync client. It targets Python 3.12+.

Out of scope: a sync client, GraphQL/v2 API support, and any TP UI/reporting
surface beyond the REST API.

## Architecture

Five layers, each with a single responsibility:

1. **Transport** (`transport.py`, `HTTPTransport`): HTTP communication over
   `httpx.AsyncClient` - base URL construction, authentication (query-param
   token or Basic auth), connection pooling, timeout configuration.
2. **Request Handler / Response Parser** (`request_handler.py`,
   `response_parser.py`): query construction, pagination, rate limiting,
   retry/backoff, and mapping HTTP error responses to typed exceptions.
   `RequestHandler` orchestrates raw dict-in/dict-out API calls;
   `ResponseParser` turns response bodies into Pydantic models (or raises
   `ParseError`) and maps error status codes to exceptions.
3. **Resources** (`resources/`): entity-specific managers (`UserStoriesResource`,
   `BugsResource`, ...) built on a shared `BaseResource[T]` generic base, plus
   `EntitiesResource` for any entity type known only at runtime.
4. **Models** (`models.py`): Pydantic v2 models for every entity type, plus
   the lightweight reference shapes (`EntityRef`, `EntityTypeRef`, `UserRef`,
   `RefWithImportance`) that nested entities and assignments arrive as. The
   definitions live in private modules grouped as TP's own type hierarchy
   groups them - `_base.py` (the base classes), `_assignables.py` (the
   `Assignable` work items), `_generals.py` (the other `General` types),
   `_lookups.py` (the lookup and people types), `_joins.py` (the join
   entities), `_content.py` (the attached-content types), `_nested.py` (the
   nested reference shapes) - and the TP `/Date(ms±HHMM)/` wire-format helpers
   (`TPDateTime`, `parse_tp_date`, `format_tp_date`) live in `_dates.py`. All
   are re-exported by `models.py`, which stays the import surface callers use;
   the private modules are not part of the public API.
5. **Client** (`client.py`, `TargetProcessClient`): the main entry point -
   wires transport, request handler, and resource managers together, and
   enforces the immutable safety mode.

Each layer only depends on the layer(s) below it; resources never talk to
the transport directly, and the client never parses raw HTTP responses
itself.

## TargetProcess API Facts

- **Authentication**: the primary scheme is an `access_token` query
  parameter appended to every request URL - TP has no header-based token
  scheme. Because the token travels in the URL, it will appear in server
  logs; the library does not enable httpx request-URL logging. The
  alternative is HTTP Basic auth (`Authorization: Basic` header) using real
  user credentials; `token` and `basic_auth` are mutually exclusive at
  construction.
- **Dates**: timestamps arrive on the wire as `/Date(ms±HHMM)/` (milliseconds
  since the Unix epoch, with an optional signed `HHMM` UTC offset appended;
  no offset means UTC). `parse_tp_date` converts this format to a
  timezone-aware `datetime`; non-matching values (already a `datetime`, an
  ISO-8601 string, `None`) pass through untouched for Pydantic's own
  handling.
- **Time dates**: TP stores a `Time` entity's `Date` **exactly as submitted**.
  It normalises nothing - there is no day anchor and no midnight coercion, so
  an entry's time-of-day is whatever its writer sent. Any apparent anchor in a
  sample is a property of that writer: across a 250-entry live sample, 154
  entries sat at midnight instance-local and 96 at midnight UTC, and the split
  tracked the *writing user* - an automated pipeline in one group, people
  using the TP UI in the other. A live write settled it: an entry submitted at
  `14:00` at `+0200` read back as that same instant, uncoerced to any day
  boundary.
  Note also that the wire offset is the **instance's** timezone, never the
  caller's - the observed instance renders a European zone with DST (`+0100`
  in March, `+0200` in August). See "Time upsert semantics" below for the
  consequence this has for `tz`.
- **Collections**: every list-returning endpoint responds with
  `{"Items": [...], "Next": <url-or-null>}`. `Next`, when present, is a
  complete continuation URL (carrying its own `skip`/`take` and any other
  query state) and must be followed **verbatim** - never recomputed from a
  local `skip` counter, since that can silently skip or repeat records if TP
  ever returns a non-linear continuation URL.
- **Bulk endpoint**: writable collections expose
  `POST /api/v1/{collection}/bulk`, taking a JSON array of entity objects -
  an object carrying an `Id` updates that entity, an object without one
  creates a new entity, and one request may mix both (vendor API reference;
  the UserStories, Projects, Features, Users and Requesters pages all
  document the endpoint this way). The vendor documents **neither the
  response body's shape nor whether a failed bulk request is atomic**; how
  the library handles both gaps is specified under "Bulk write semantics"
  below.
- **Priorities**: scoped by entity type, not by project or process. A
  `Priority` record carries an `EntityType` reference and no `Project` or
  `Process` field — asking for either (`include=[Process]`,
  `where=Process.Id eq …`) is rejected with HTTP 400. Names repeat across
  entity-type sets ("Must Have" is a distinct record for UserStory, Feature,
  Epic and PortfolioEpic) and are unique within one set, so
  `where=EntityType.Name eq '<Type>'` narrows the instance-wide list to the
  set in which a name identifies exactly one Id. Supplying a priority by
  name, or an Id belonging to another entity type, fails the write with
  HTTP 403 rather than 400.

## Public API Surface

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
- `create(**fields) -> T` (READWRITE only)
- `update(id, **fields) -> T` (READWRITE only)
- `delete(id) -> None` (READWRITE only)
- `create_many(items) -> list[T]` / `update_many(items) -> list[T]`
  (READWRITE only) - one bulk request for the whole batch; see "Bulk write
  semantics" below. On a collection the server restricts (next paragraph)
  they raise `ReadOnlyViolation` in every mode, as the single-item writes do

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

`times` additionally provides `find_for_day` and `upsert` - see "Time upsert
semantics" below.

`priorities` additionally exposes the entity-type-scoped lookups that make a
priority name resolvable: `for_entity_type(entity_type) -> list[Priority]`
returns the valid set, and `resolve(name, *, entity_type) -> Priority` returns
the single match — raising `NotFoundError` when nothing matches (listing the
names that do) and `AmbiguousMatchError` when several do, so a caller never
receives a guessed Id.

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
collections (Context, EntityStateHistory, Revisions, RevisionFiles, Messages,
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
and TP documents no bounds on effort, progress or flow metrics to assert.
`RoleEffort` and `Time` keep the bounds they were published with, and
`times.upsert` validates on the write side, where the value originates and a
range error is actionable.

`custom_fields` (`CustomFields`) sits on the `Entity` base, so custom-field
values are reachable on every entity type: fetched with
`include=[CustomFields]`, the payload's `CustomFields` array parses into a
`list[CustomFieldValue] | None` rather than landing raw in `model_extra`.

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

## Behavioural Contracts

### List semantics

`list()` (on every typed resource, `EntitiesResource`, and `RequestHandler`
itself) takes:

- `where`: a TP `where=` filter expression, passed through verbatim with no
  client-side transformation.
- `include`: optional field list, rendered as `include=[Field1,Field2]`.
- `exclude`: optional field list, rendered as `exclude=[Field1,Field2]` -
  server-side removal of fields from each item (the complement of
  `include`).
- `result_include`: optional field list, rendered as
  `resultInclude=[Field1,Field2]` - narrows each item to exactly the named
  fields, reducing payload size server-side (as `include` and `exclude` do,
  and for the same bandwidth-and-token reasons).
- `append`: optional list of calculated fields (e.g. `Tasks-Count`),
  rendered as `append=[Field1,Field2]`.
- `innertake`: optional bound on the size of nested collections hydrated
  via `include`, rendered as a plain integer; negative raises `ValueError`.
- `order_by` / `order_by_desc`: optional server-side sort field, ascending /
  descending, rendered as `orderBy=` / `orderByDesc=` with the field passed
  through verbatim. Passing both raises `ValueError`: each direction is
  live-verified individually and their combination is undefined, so it is
  refused rather than sent.
- `skip`: optional server-side offset before the first yielded item -
  deliberately opt-in, see below; negative raises `ValueError`.
- `limit`: the maximum **total** number of items yielded across all pages
  (`None` = unbounded). `limit=0` yields nothing and makes no network
  request at all - though argument validation still runs first, so an
  invalid combination raises rather than vanishing behind an empty
  iteration.
- `page_size`: the page size (`take=`) used for each underlying request,
  independent of `limit`. The first request's `take` is `min(page_size,
  limit)` when `limit` is set, otherwise `page_size`.

Because `list()` is an async generator, its `ValueError`s surface when
iteration begins, not at the call itself.

`get()` accepts the same payload-shaping parameters (`include`, `exclude`,
`result_include`, `append`, `innertake`); the sort and offset parameters are
list-only, being meaningless on a single entity.

Pagination follows the server-provided `Next` URL verbatim for every
subsequent request - the client never reconstructs `skip` itself, so a
short or irregular page never silently drops or duplicates items. Before
following it, `Next` is checked against the transport's base URL (same
scheme, host, and port); a relative `Next` resolves against the base and
so always passes, but a mismatched absolute `Next` raises `NetworkError`
rather than being followed - the client would otherwise leak the
`access_token` (carried on every request) to whatever host the response
named.

**Offset paging (`skip`) is opt-in, never the default.** The forward-only
`Next` walk above is a genuine safety property, which is why `skip` does not
replace it: passing `skip` positions where iteration *starts* (it is sent on
the first request only), after which pagination still follows the server's
`Next` URL verbatim, carrying the server's own continuation offsets. A
caller who instead pages manually - one `list(skip=...)` call per page -
takes on the classic offset-paging hazard the `Next` walk exists to avoid:
items shifting between requests silently drop or duplicate records.

**`prettify` is deliberately not exposed.** TP supports it (verified live)
but it only pretty-prints the JSON wire payload for human inspection;
through this library's parsed-model API it has no observable effect, so it
earns no API surface. Anyone debugging raw HTTP can append `prettify` to a
URL by hand.
### Bulk write semantics

`create_many` / `update_many` (on every typed resource and, with a leading
`entity_type` argument, on `entities`) send the whole batch as a single
`POST /{collection}/bulk` request - one slot against the rate limiter
instead of one request per entity. `RequestHandler.bulk` is the shared
dict-in/dict-out path underneath both.

- **One wire shape, two methods.** The endpoint itself decides
  create-vs-update per item by the presence of an `Id`, so each method
  validates the shape it promises before any request is sent:
  `create_many` raises `ValueError` on an item carrying an `Id` (on the
  wire it would silently update an existing entity), and `update_many`
  raises `ValueError` on an item without one (it would silently create).
  The key is matched case-insensitively (`id` counts as `Id`) - the wire
  field is `Id`, but TP's JSON handling is not documented as
  case-sensitive, and the check exists to catch exactly the mistakes a
  strict comparison would wave through. A caller who genuinely wants a
  mixed batch makes two calls.
  `update_many` then sends the identifier under the wire key `Id` whatever
  casing it received, so a non-canonical key is never forwarded as-is (on
  the wire an item without `Id` is a create); an item that spells the key
  more than once (`Id` and `id` together) is rejected as ambiguous.
- **Never auto-retried.** A bulk request is a mutation, so the retry
  policy below applies unchanged: 429 and 5xx surface immediately as
  `RateLimitError`/`APIError`.
- **No atomicity assumption.** TP does not document whether a failed bulk
  request is atomic, so after an error a caller must not assume nothing
  was written - part of the array may have been applied, and re-reading is
  the only way to know. This is the same stance the retry policy takes for
  single mutations under 429.
- **Response parsed defensively.** The response body is not
  vendor-documented either; a bare JSON array and an `Items`-wrapped
  object are both accepted (each item then parsing into the resource's
  model as usual), every element of that array must be an object, and
  anything else raises `ParseError` rather than being guessed at.
- **Empty input short-circuits.** An empty `items` returns `[]` with no
  network request - after the write gates have run, so a READONLY client
  is refused even for an empty batch.

### Retry policy

The request handler retries HTTP 429 and 5xx, but only for safe methods
(GET/HEAD/OPTIONS). Mutating methods (POST/PUT/DELETE) are never
auto-retried, on 429 or 5xx alike:

- **GET/HEAD/OPTIONS retry on 429 or 5xx.** These methods have no side
  effects, so re-sending is always safe.
- **POST/PUT/DELETE never auto-retry.** TargetProcess documents no
  guarantee that a 429 response means a mutation was not processed, and
  offers no idempotency keys - so retrying risks duplicating the mutation.
  Both 429 and 5xx therefore surface immediately (`RateLimitError`/
  `APIError`) on these methods; a caller who knows a specific mutation is
  safe to retry owns that decision itself. The bulk endpoint is a POST and
  inherits this unchanged - a retried bulk request could duplicate every
  create in the batch.

Up to 3 retries (4 attempts total) with exponential backoff: `0.5s * 2^attempt`,
capped at 30 seconds per delay. A `Retry-After` response header, when
present, is honoured in place of the computed delay:

1. Parsed first as numeric delta-seconds.
2. If that fails, parsed as an HTTP-date (`email.utils.parsedate_to_datetime`)
   and converted to a delay via `(parsed_date - now_utc).total_seconds()`.
3. If both parses fail, the exponential schedule is used instead.

Every branch's result is floored at 0 seconds and capped at 30 seconds
before use. Once retries are exhausted (or a non-retryable status arrives),
the last response is mapped through the normal error-handling path, so a
persistent 429/5xx surfaces as `RateLimitError`/`APIError` rather than a
bespoke retry exception.

A transport-level failure (no response received at all - connection error,
timeout, DNS failure) is never retried; it always raises `NetworkError`
immediately.

### Rate limiting

Every attempt (including retries) acquires the async rate limiter
(`easylimit`, 100 requests/minute) before being sent, via its async context
manager - never a blocking synchronous acquire, so concurrent requests
genuinely interleave rather than serialising on the event loop.

### Readonly safety mode

`TargetProcessClient` takes a required `mode: ClientMode` (`READONLY` or
`READWRITE`) at construction. The mode is:

- **Frozen after `__init__` completes.** `__setattr__` rejects any further
  assignment to `mode`, `_mode`, or `_mode_frozen` once the freeze flag is
  set - a best-effort guard against ordinary attribute assignment, not a
  hard sandbox (it doesn't stop `object.__setattr__` or similar
  escape hatches).
- **Enforced at two layers.** Every resource's `create`/`update`/`delete`
  checks `client._check_write_permission()` before calling the request
  handler; the request handler itself also calls an injected
  `check_write` callback before every write, so a write is refused even if
  a caller constructs a `RequestHandler` directly and bypasses the resource
  layer. `READONLY` raises `ReadOnlyViolation` from whichever layer catches
  it first.

### Time upsert semantics

`times.upsert` is the one resource method that is not a direct TP API
operation. TP has no upsert primitive, so it composes a find with a create or
update, keyed on `(assignable, user, day)`.

- **The day is the caller's to define.** `when` must be timezone-aware
  (`ValueError` otherwise); `tz` defaults to `when`'s own offset. TP stores
  `Date` as the instant supplied and normalises nothing (see "Time dates"
  above), so `find_for_day` queries a window a day wider on each side and
  makes the exact-day decision client-side by projecting each stored instant
  into `tz`. **Read in the same zone you wrote in.** Which calendar day an
  instant falls on is a function of `tz`, so a reader projecting into a
  different zone from the writer resolves a near-midnight entry onto the
  adjacent day: the entry is missed, `upsert` creates a duplicate for what
  looks like an empty day, and from then on that day raises
  `AmbiguousMatchError` until a human resolves it. Confirmed live: an entry
  written at `00:30` at `+0200` is re-found by a `+0200` reader and missed by
  a UTC one. Pass the same `tz` on every call that touches a given key -
  whichever zone the writing side uses.
- **`upsert` has no locking.** It is find-then-create/update, and TP has no
  unique constraint on `(Assignable, User, Date)` to fall back on, so two
  overlapping `upsert` calls for the same key can both find nothing and both
  create - concurrency safety is the caller's responsibility. A duplicate
  wedges that day's key with an `AmbiguousMatchError` on every subsequent
  call until a human resolves it; `find_for_day` is the tool for finding and
  resolving it.
- **Only supplied fields are synced.** `spent`, `description`, `remain` and
  `is_estimation` are compared against the existing entry; an omitted field is
  neither compared nor written. `Assignable`, `User`, `Date`, `Project` and
  `Role` are identity and are never updated.
- **`spent` is sent as given.** No rounding is applied. Passing more precision
  than the instance stores makes TP quantise on write, so every subsequent
  call sees a difference and updates again; quantise before calling.
- **`description` is stripped before comparing and writing.** `Entity` sets
  `str_strip_whitespace=True`, so a stored description is always read back
  stripped; a supplied `description` is stripped the same way before it is
  compared and before it is written, so a leading/trailing-padded value
  converges instead of updating on every call.
- **More than one match raises.** `AmbiguousMatchError`, rather than picking
  one arbitrarily and making repeated syncs non-deterministic.
- **`dry_run=True` writes nothing** and reports `would_create` / `would_update`
  / `unchanged`. It works on a READONLY client. With `dry_run=False`, a
  READONLY client raises `ReadOnlyViolation` when a write is reached — an
  `unchanged` outcome reaches no write and so returns normally in either mode.

```python
result = await client.times.upsert(
    assignable_id=51383,
    user_id=1,
    when=datetime(2026, 8, 9, 14, 0, tzinfo=timezone(timedelta(hours=2))),
    spent=2.5,
)
# result.action -> UpsertAction.CREATED | UPDATED | UNCHANGED
# result.changed_fields -> frozenset of model field names written
```

## Observability

Runtime observability lives in `targetprocess/_observability.py` and is
scoped to what a *library* should own. The application that embeds the
library owns the rest (metrics, alerting, error tracking, deployment
observability, product analytics) - it has the deployment context a
library cannot assume.

### Implemented signals

- **Structured logging.** A dedicated `logging.getLogger("targetprocess")`
  with a `NullHandler` by default (silent unless the application attaches a
  handler). `StructuredJsonFormatter` emits one JSON line per record
  (`ts`, `level`, `logger`, `msg`, `request_id`, plus caller extras).
  `get_logger("name")` returns a child under the `targetprocess` namespace.
  `RequestHandler._request` emits structured `request.start` /
  `request.complete` / `request.retry` / `request.error` /
  `request.transport_error` records.
- **Log scrubbing.** `ScrubbingFilter` redacts the `access_token` query
  param and `Authorization: Basic|Bearer` header values from the records
  this library emits. It is attached to the `targetprocess` logger and to
  every child `get_logger()` returns - both, because a filter on a logger
  runs only for records logged *through* that logger, not for records
  propagated up from a child. It pre-formats and redacts the message, the
  `url` extra, the `headers` extra, and every other string-valued extra
  (an extra such as `{"error": repr(exc)}` can carry a request URL the
  message never mentions); `StructuredJsonFormatter` additionally scrubs
  the formatted traceback, which is rendered from `exc_info` after the
  filter has run. `scrub_url`, `scrub_message`, and `scrub_headers` are the
  underlying helpers. The scrub is deliberately
  narrow to the two real secret surfaces this library produces (TP carries
  the token as a query param, and Basic auth is the header alternative); it
  does not run a generic token-shaped regex, which would redact legitimate
  entity IDs, hashes, and long identifiers that appear in normal log
  content. This closes the token-leak surface the README already warns about
  for httpx request-URL logging, *in this library's own records*. The filter
  cannot reach records emitted by other libraries - `httpx` and `httpcore`
  log their own request URLs - nor a logger obtained by calling
  `logging.getLogger("targetprocess.x")` directly instead of via
  `get_logger()`. An application that wants blanket redaction should attach
  a `ScrubbingFilter()` instance to its own handler, which every propagated
  record passes through whatever logger produced it.
- **Distributed tracing (correlation-ID propagation).** A `ContextVar`
  request ID is stamped on every outgoing request as an `X-Request-ID`
  header by the transport's request event hook, and bound to every log
  record `RequestHandler` emits. `new_request_id()` generates an ID,
  `current_request_id()` reads the bound one, and
  `request_id_context(rid)` binds one for a scope (so a caller's request
  context flows into both the wire header and the library's logs). A
  caller-supplied `X-Request-ID` header is never overwritten. When no ID is
  bound, the transport generates one so every request is still traceable.
  Because the bound ID typically originates from an inbound request, it is
  untrusted input: `request_id_context` strips characters outside the
  printable-ASCII header field-value range, trims and length-caps the
  result, and falls back to a generated ID if nothing usable remains - so a
  CR/LF cannot split the header or fail every request in that scope.

### Won't-fix (not applicable to a client library)

The remaining Debugging & Observability readiness signals are deliberately
not implemented, because they are deployment/organisation concerns owned by
the application that embeds this library, not by the library itself. A
library that shipped its own Sentry, alerting, or product-analytics
integration would impose a specific vendor and deployment shape on every
caller - the opposite of the minimal-dependency posture this library takes
(`httpx`, `pydantic`, `easylimit`, and the stdlib only).

- **metrics_collection** - won't-fix. A library has no global runtime to
  sample; metrics belong to the embedding application, which already has a
  metrics backend. `RequestHandler`'s structured logs (`status`,
  `attempt`, `delay`, `request_id`) are the lightweight, vendor-neutral
  substrate an application can count into its own metrics.
- **error_tracking_contextualized** - won't-fix. Bundling Sentry/Bugsnag
  would add a hard dependency and a vendor choice the library should not
  make. Callers catch `TargetProcessError` (or a subclass) and forward it
  to whatever error tracker they run; the `request_id` on the log records
  gives the correlation context.
- **alerting_configured** - won't-fix. Alerting is a property of an
  operated system, not a library. There is no deployment here to alert on.
- **deployment_observability** - won't-fix. The library has no deployment
  pipeline, runtime, or infrastructure to observe.
- **product_analytics_instrumentation** - won't-fix. A library does not
  have end-users to instrument; product analytics are the application's
  responsibility.
- **error_to_insight_pipeline** - won't-fix. This is an aggregation
  concern over an organisation's error/metrics stores; it operates on the
  application's observability backends, not on a library's emit site.

## Testing Approach

Moved to [docs/testing.md](docs/testing.md): the unit/integration split, the
write-path recording rules, cassette sanitisation at record time, and the
cassette guard.

## Tooling Gates

- **Package management**: `uv` (Python 3.13, pinned via `.python-version`
  and `.tool-versions`; the library floor stays `requires-python >=3.12`).
- **Lint & format**: `ruff check .` and `ruff format --check .`. The lint
  selection includes `N` (pep8-naming) and `C901` (mccabe, capped at
  complexity 10). Two naming exemptions are declared explicitly rather than
  left implicit: `_base.py` keeps the PascalCase property accessors on
  `Entity`/`NamedEntity` because they mirror the wire format TP returns (a
  per-file ignore in `pyproject.toml`; `models.py` is the re-export surface),
  and `ReadOnlyViolation` keeps its published name instead of gaining an
  `Error` suffix (a `noqa` at its declaration).
- **Types**: `mypy --strict src`.
- **Tests & coverage**: `pytest` with branch coverage over `src`, gated at
  `--cov-fail-under=90`.
- **Pre-commit hooks** (`.pre-commit-config.yaml`): the local mirror of the
  gates above, so a failure lands before the push instead of in a CI log.
  Fast checks (ruff, ruff format, the repo checks below, and the
  upstream `pre-commit-hooks` set: large added files, YAML/TOML validity,
  merge-conflict markers, private keys, EOF/whitespace) run on commit;
  `mypy --strict src` runs on push, being too slow to gate every commit and
  meaningful only over the whole package. Ruff and mypy run via `uv run`, so
  the hook versions are exactly the ones in `uv.lock` — no second pinning to
  drift.
- **File size** (`scripts/check_large_files.py`): fails a tracked file over
  1000 lines or 256 KiB. Generated artefacts whose size is not a design
  decision (`uv.lock`, cassettes) are exempt.
- **Debt markers** (`scripts/check_todos.py`): every `TODO`, `FIXME`, `HACK`
  or `XXX` in code must name the issue tracking it - `TODO(#123): ...`. An
  unattributed marker never reaches a board, so it is debt nobody owns. Prose
  files are not scanned: a marker in Markdown is documentation about markers,
  not debt in a code path.
- **Internal references** (`scripts/check_internal_refs.py`): fails a tracked
  file naming a tracker issue or an agent session. The reference shape is
  generic - an upper-case key of two to six characters, a dash, and up to six
  digits - rather than a list of keys: publishing that list would leak the very
  thing the check exists to keep out, and would miss any key added later.
  Matching is case-sensitive, because lower-cased the same shape also matches
  every locked dependency version and every GUID fragment in the tree.
  `EXCLUDED_PREFIXES` carries the public standards designations that share the
  shape. Prose *is* scanned here, unlike the debt-marker check above - a dead
  reference in the README is the case that matters most. `ALLOWED_PATHS` names
  the files permitted to carry references, by path alone: recording the
  reference itself would put back the thing the generic shape exists to avoid.
  An entry exempts references only - a session URL or trailer is refused in
  those files too - and it lapses as soon as the file stops carrying any
  reference, which a test asserts, so an exemption cannot outlive its cause.
- **Model field coverage** (`scripts/check_model_coverage.py`): diffs each
  model's declared aliases against its type's `/api/v1/{collection}/meta` and
  reports coverage per model, in both directions - a field TP declares that the
  model does not, and a field the model declares that TP does not. GET-only,
  and **not** a CI gate: it needs a live instance and a real token, neither of
  which CI has. `--fail-under` makes it one where a caller does have both.

  Three things fail a run besides a coverage shortfall, each a case that would
  otherwise pass quietly: a declared field absent from `/meta`; a dead
  `EXCLUDED` / `KNOWN_DEVIATIONS` entry, whose purpose is to keep a decision
  visible and which stops doing anything once it no longer applies; and a
  `/meta` body reporting no properties at all, which is a failed measurement
  rather than full coverage.

  `--validate` additionally fetches real records and parses them through each
  model - the check `/meta` cannot make, since it says which properties exist
  and not what TP puts in them. Declaring a field can turn a payload the models
  used to tolerate into a hard parse failure, and no offline fixture shows it: a
  `Bug`'s `EntityType` arriving with no `Id` is exactly that case. A model whose
  sample cannot be fetched is reported as **not checked** and fails the run,
  because silence from a model that was never exercised is not evidence it
  parses.
- **Copy-paste detection** (`.jscpd.json`): jscpd over Python sources, failing
  above 3% duplication (currently ~2%). Node-only tooling, so it runs in CI
  rather than requiring a Node toolchain on every dev machine.
- **CI** (`.github/workflows/ci.yml`): five job definitions, expanding to six
  job runs because `test` is a two-value matrix, on every push to `main` and
  every pull request - `test` (uv sync, ruff check, ruff format check, mypy
  strict, pytest with the coverage gate; a matrix over Python 3.12 and 3.13,
  with `UV_PYTHON` overriding the `.python-version` pin per leg), `quality`
  (`pre-commit run --all-files` for each of the `pre-commit` and `pre-push`
  stages, which also proves the hook config itself still works),
  `duplication` (jscpd), `audit` (pip-audit over the exported, hashed
  `uv.lock` with every extra; any known vulnerability fails the job), and
  `build` (`uv build`, `twine check --strict`, and an import of the built
  wheel from a clean environment).
- **Release** (`.github/workflows/release.yml`): on a `v*` tag, builds the
  distributions, refuses a tag whose commit is not on `main` or whose name
  disagrees with the wheel's version, and publishes to PyPI by trusted
  publishing (OIDC) under the `pypi` GitHub environment. No token is stored;
  the environment's protection rules are the manual gate on a publish.
