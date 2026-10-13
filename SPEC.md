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
- **Unrecognised query input**: TP answers a query parameter it does not
  recognise, and a `where=` naming a nested collection path it does not filter
  on, with HTTP 200 and the unfiltered, unsorted rows - indistinguishable from
  success. The confirmed case is a filter on the `Assignments` collection of an
  assignable, which returns the same rows as the unfiltered request, while the
  `Assignment` entity's own `GeneralUser.Id` filter applies. A collection
  `Count` is the loud exception, rejected with HTTP 400 - `Comments.Count` too.
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
- **Context**: `GET /api/v1/Context?format=json` returns the authenticated
  context rather than a collection - no `Items` envelope, no per-record Id -
  so it is not addressable through the entity surface. Verified against a live
  TargetProcess instance with an administrator token (HTTP 200): the acting
  user is the top-level `LoggedUser` object, carrying `Id` (int), `Email`,
  `FirstName`, `LastName`, `Kind` and `ResourceType` (str), `IsActive` and
  `IsAdministrator` (bool) - and no `Login`. Alongside it the payload carries
  `Processes` (each with nested `CustomFields`, `Practices` and `Terms`
  collections), `SelectedProjects` (each with `Process` and `Program`),
  `SelectedTeams`, a workspace-wide `CustomFields` collection, `GlobalTerms`,
  `Culture`, `AppContext`, `Acid`, `Edition`, `Version` and four booleans - a
  heavy payload for an identity lookup. `Terms` and `GlobalTerms` hold the
  instance's renamed entity terms, `Term` records carrying `WordKey` and
  `Value`. Whether a non-administrator token can read Context, and whether the
  endpoint honours `include=`, are unverified; the client does not request it.
- **LoggedUser**: `GET /api/v1/Users/LoggedUser?format=json` returns the
  `User` entity of the request's credential. Verified against a live
  TargetProcess instance with an administrator token (HTTP 200): the same
  top-level fields as `GET /api/v1/User/{id}` - every `User` model field but
  `AvatarUri`, `Login` included. Non-administrator access is unverified.
- **Entity states**: a work item carries two entity states that move
  independently - the project-workflow state on the item (`EntityState`) and
  the team-workflow state on each of its `TeamAssignment` records (the lane a
  team board shows). Each state's `Workflow` reference names its workflow;
  where the team has no workflow of its own the team assignment carries the
  item's own state object (observed with `Workflow.Id` 1, the project
  workflow), so a second write would be a no-op.

## Public API Surface

Moved to [docs/public-api.md](docs/public-api.md): client construction, the
acting user, the resource managers and their write surface, typed versus
generic coverage, the models, and the exception hierarchy.

## Behavioural Contracts

### List semantics

`list()` (on every typed resource, `EntitiesResource`, and `RequestHandler`
itself) takes:

- `where`: a TP `where=` filter expression, passed through verbatim with no
  client-side transformation once the refusal under *Silently ignored
  queries* below has passed.
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

### Silently ignored queries

**Query parameters.** `QUERY_PARAMETERS` in `request_handler.py` names every
parameter the handler sends - `format`, `take`, `skip`, `where`, `orderBy`,
`orderByDesc`, `include`, `exclude`, `resultInclude`, `append` and
`innertake` - and `RequestHandler.get` and `RequestHandler.list` refuse a built
parameter set carrying any other name with `ValueError` before the URL is
formed. Every parameter reaches the wire through a typed keyword, so the check
guards the builders themselves. `access_token` is the transport's, merged in
at send time, and outside the set; `prettify` stays deliberately absent (see
above).

**Filter paths.** `BaseResource.ignored_filter_paths` maps the leading segment
of a `where=` path TP will not filter on for a collection to the reason and the
route to use instead. The known set is declared once, as
`ASSIGNABLE_IGNORED_FILTER_PATHS` in `resources/base.py`, and referenced by the
six assignable managers (`UserStory`, `Bug`, `Task`, `Feature`, `Epic`,
`Request`). `check_where` applies it on `list()` only - never on `get()`,
`order_by` or `include` - matching a path's leading segment in any casing
outside quoted values, and refuses with a `ValueError` naming the collection
and the route. `entities` mirrors the refusal for every spelling of those six
collections and of the untyped Assignable-derived collections confirmed so far -
`Assignable`, `PortfolioEpic`, `TestPlanRun`, `InboundAssignable` and
`OutboundAssignable`, in `_UNTYPED_ASSIGNABLE_COLLECTIONS`. That is what has
been checked, not every candidate; the TestPlan family is unexamined.

| Ignored path | Route instead |
| --- | --- |
| `Assignments.*` on the assignable collections | query `assignments` by `GeneralUser.Id` with `include=["Assignable"]` |

An entry is added only with live evidence: an unfiltered control returning the
same rows. `RequestHandler.list` itself still passes `where` verbatim; the
refusal is the resource layer's, as the include refusal is.

### Derived-field writes

`BaseResource.derived_fields` maps a wire field name TP computes from another
collection to the reason and the route that sets the value. The known set is
declared once, as `ASSIGNABLE_DERIVED_FIELDS` in `resources/_derived.py`: a work
item's three effort roll-ups - `Effort`, `EffortCompleted`, `EffortToDo` - each
the sum of the corresponding field over its `RoleEfforts`. `AssignableResource`
carries it for the six work-item managers, and `entities` mirrors it for every
spelling of their collections and of the untyped Assignable-derived ones, so the
generic accessor cannot sidestep the typed guard.

`create`, `update`, `create_many` and `update_many` refuse a field named there
with `ValueError` before any request is sent (`check_derived_fields`, and per
batch item `check_derived_items`), matching the name case-insensitively and
stripped as the verification comparison does. The message names the field, the
collection, the reason and the RoleEffort route; a bulk refusal names the item's
zero-based position, as that path's `Id` guards do. `ValueError` rather than
`ReadOnlyViolation`, which answers "this client, or this collection, may not
write at all". The route is the `(Assignable, Role)` row, through `role_efforts`.

The refusal is before the request because nothing after it settles the question.
The recorded write suite evidences that such a write *can* land - it sends
`Effort` and an independent re-read shows it - while the same field is reported as
a sum over `RoleEfforts`, so a write can equally be recomputed away. Both carry a
success status, and no re-read separates "stored because nothing overrode it" from
"recomputed back to the same number". That a write lands where the item has no
`RoleEffort` rows and is reconciled away where it has is the likely explanation,
but it is inference from those recordings, not established behaviour, and this
contract does not rest on it.

`allow_derived=True` on any of the four methods sends the write anyway, for a
caller who knows the item's `RoleEfforts`; the recorded write suite is that
caller, which is what keeps `Effort` usable there as the numeric field a test can
prove TP applied. Only the declared set is refused - `Progress`, `TimeSpent`,
`TimeRemain`, `LeadTime` and `CycleTime` are computed too and are not declared,
each needing its own route in its own message and the same live evidence an
ignored-filter entry is added on - and `RoleEffort`'s own effort fields are stored
as written.

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

### Verified writes

An update's return value is TP's own echo of the write, which can be stale.
`update(..., verify=True)` and `update_many(..., verify=True)` on the typed
managers (not `entities`) re-read each entity with one GET narrowed to the
requested keys, after the whole batch for `update_many`, and return the
re-read models, which carry `Id`, `ResourceType` and those keys (every other
field `None`); a requested field not observed raises one `VerificationError`
carrying integer entity Id -> field -> `(requested, observed)`. A verified
write refuses, before sending, a `CustomFields` entry that is not a mapping
with a string `Name`, and a verified `update_many` a repeated Id or one that is
neither an integer nor a string of ASCII digits. References match by `Id`,
`None` matches null or an absent key, numbers compare numerically, strings
stripped, wire dates on the instant, and `CustomFields` (any sequence but a
string, bytes or bytearray) entry by entry by name; any other absent key fails.
Nothing converts between forms, so a string never matches a number. A
`Description` sent without the Markdown marker is stored HTML-encoded, so it can
fail on its own encoding.

### Unscheduling: a verified TeamIteration clear

A child created with a `Team` and no `TeamIteration` inherits its parent's
sprint at creation: the create echo and the read that follows carry the
parent's `TeamIteration`. An explicit `null` on such a child takes effect, as
it does on a child given the sprint directly - in both recorded configurations
the verifying re-read carries the key present and null. TP was reported to
answer a child's explicit `null` under a scheduled parent with a success status
while discarding it, leaving an item that should be unscheduled silently
scheduled; no configuration tried has reproduced that, but a success status
alone could not reveal it. The six work-item managers therefore expose
`clear_team_iteration(id) -> T`, which is `update(id, TeamIteration=None,
verify=True)` and nothing more: the same write, the same single narrowed
re-read and the same comparison as any other verified write, so an absent key
counts as cleared and an item that already had none verifies. A failure is
re-raised as `TeamIterationCascadeError`, a defensive guard kept for that
reported discard, whose remedy would not be a retry: the reported case involved
a scheduled parent, so where the item has a parent, that is the first thing to
inspect. There is deliberately no `verify=False`: an unverified clear cannot be
told from a failed one, which is the method's whole reason for existing, so a
caller wanting the bare write calls `update` directly.

### Entity-state transitions

The six work-item managers (`AssignableResource`) expose
`entity_state_levels(id) -> StateLevels` and
`advance_state(id, *, to, team_to=None, verify=True) -> StateLevels`. Each
target (Id, name or `EntityState`) resolves within its own level's workflow.
Levels whose workflow Ids are equal are collapsed: one write, and `team_to`
absent or naming the same state. A distinct team level without `team_to`
raises `SplitTransitionError` naming both workflows, before any write; more
than one team assignment raises `AmbiguousMatchError`. Writes go item then
team, unlocked; `verify` re-reads each level after its own write (a collapsed
team level after the item's), so an item write that did not apply raises
`VerificationError` before the team level is written.

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

Moved to [docs/observability.md](docs/observability.md): the structured logger,
the log scrubbing, request-ID propagation, and the readiness signals left to the
application that embeds the library.

## Testing Approach

Moved to [docs/testing.md](docs/testing.md): the unit/integration split, the
write-path recording rules, cassette sanitisation at record time, and the
cassette guard.

## Tooling Gates

Moved to [CONTRIBUTING.md § Quality gates](CONTRIBUTING.md#quality-gates).
