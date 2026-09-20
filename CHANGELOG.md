# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `list()` refuses a `where=` filter naming the `Assignments` collection on four
  further collections - `PortfolioEpics`, `TestPlanRuns`, `InboundAssignables`
  and `OutboundAssignables` - raising `ValueError` before any request is sent,
  as it already did for the six typed assignable collections. TargetProcess
  answers such a filter with HTTP 200 and the *unfiltered* rows, so code that
  appeared to narrow one of these collections by assignee was in fact receiving
  every row; it now raises rather than returning silently-wrong results. Each
  collection was confirmed against an unfiltered control on the same collection
  before being added. Only `list()`'s `where=` is affected - reading
  `InboundAssignables` or `OutboundAssignables` through `include=` is unchanged.
- The refusal's message states both ways a path under `Assignments` fails: a
  filter on one of the collection's fields is accepted and ignored (HTTP 200),
  while `Assignments.Count` is rejected by the query parser (HTTP 400).

### Fixed

- The eight numeric fields on the `RoleEffort` and `Time` read models no longer
  carry a `ge=0` bound - `InitialEstimate`, `Effort`, `EffortCompleted`,
  `EffortToDo`, `TimeSpent` and `TimeRemain` on `RoleEffort`, and `Spent` and
  `Remain` on `Time`. Each is supplied by the server, and a constraint on a
  server-supplied value fails the *whole entity* rather than the field, so one
  out-of-range record would have aborted an entire `list()` page with a
  `ParseError` - the rule `AssignableEntity` already stated and these two models
  broke. A consumer relying on `ValidationError` for a negative value on these
  fields, including on assignment, no longer receives one; `times.upsert` keeps
  its write-side check, where a range error is actionable.
- `Time`'s class docstring and its `project` field description say what a
  custom-activity entry's `project` holds. Such an entry has no `Assignable`,
  and the field is populated all the same, matching that activity's own project
  on every entry observed.

## [0.2.1] - 2026-09-18

### Fixed

- A verified clear of a custom field (`update(..., verify=True)` or
  `set_custom_field(id, name, None)`) no longer raises `VerificationError`
  when the field reads back `False` or `0`. The re-read comparison now
  accepts any of TargetProcess's empty-equivalent values - null, `""`,
  `False` or `0` - as showing a requested clear, rather than only null or
  `""`. This fixes clearing a `CheckBox` custom field, which reads back
  `False`, and a numeric one, which reads back `0`; a *set* value of `False`
  or `0` is unaffected and still compares exactly as before.

## [0.2.0] - 2026-09-17

The first beta release.

### Added

- `users.logged_user()`: resolves the user the client's credential
  authenticates as with one `GET /api/v1/Users/LoggedUser`, returning the
  `User` model, cached per client instance. `RequestHandler.logged_user()` is
  the fixed-path read beneath it.
- `update()` and `update_many()` take an opt-in, keyword-only `verify=True`:
  after the write each entity is re-read with one independent GET narrowed to
  the requested keys, the re-read model is returned instead of TargetProcess's
  own echo, and a requested field that is not observed raises the new
  `VerificationError`, which carries every mismatch and survives a pickle
  round trip. A verified write refuses, before sending, a `CustomFields` entry
  that is not a mapping with a string `Name`. The default path is unchanged.
- `set_custom_field(id, name, value)` on every typed manager sets a
  custom-field value by name, or clears it when `value` is `None`, sending
  `{"CustomFields": [{"Name": ..., "Value": ...}]}`. It re-reads the entity by
  default and raises `VerificationError` when the value, or the clear, did not
  land, or no field of that name came back.
- `entity_states.for_workflow(workflow_id)`, `entity_states.resolve(name, *,
  workflow_id)` and `entity_states.final_states(workflow_id)`: the states of
  one workflow, a state name resolved within that workflow (raising
  `NotFoundError` or `AmbiguousMatchError` rather than guessing), and the
  workflow's final states.
- `entity_state_levels(id)` and `advance_state(id, *, to, team_to=None,
  verify=True)` on the six work-item managers, through their new shared base
  `AssignableResource`: a work item's project-workflow and team-workflow
  entity states read together as `StateLevels` (of two `LevelState`s), and
  moved as one transition - each target resolved within its own level's
  workflow, one write where both levels share a workflow, and the new
  `SplitTransitionError`, which survives a pickle round trip, raised before
  any write when a distinct team level would be left behind.

### Changed

- Development status moves from Alpha to Beta (the
  `Development Status :: 4 - Beta` classifier), and the README states what
  1.0.0 requires.
- `list()` refuses, before any request is sent, a `where=` filter naming a
  nested collection path TargetProcess accepts and silently ignores -
  currently `Assignments.*` on the assignable collections (`UserStory`,
  `Bug`, `Task`, `Feature`, `Epic`, `Request`, and `Assignable` through
  `entities`), which answer HTTP 200 with the unfiltered rows. The
  `ValueError` names the join-entity route: query `assignments` by
  `GeneralUser.Id`.
- Every query-parameter name the request handler puts on an entity-API
  request is declared in one allowlist (`QUERY_PARAMETERS`), and a name
  outside it is refused before the request is built rather than sent for
  TargetProcess to ignore. The `access_token` the transport merges in at
  send time is not part of the allowlist.
- The relation examples in the `relations` and `relation_types` docstrings,
  and the relations read in `scripts/live_smoke.py`, use the current
  `Inbound`/`Outbound` names in place of the deprecated `Master`/`Slave`: the
  create, the `Outbound.Id` filter and the include.

### Fixed

- `ReadOnlyViolation` raised with an operation and a resource now survives a
  pickle round trip with its message and attributes; it used to come back
  with the generic readonly-mode message. Every library exception now pickles
  through one mechanism on `TargetProcessError`.

## [0.1.0] - 2026-09-08

The first public release.

### Added

- `TargetProcessClient`: an async client for the TargetProcess v1 REST API,
  built on `httpx`, with a required and immutable `mode` (`READONLY` /
  `READWRITE`) enforced at both the resource and request-handler layers.
- Authentication via the `access_token` query parameter (TargetProcess's token
  scheme) or HTTP Basic auth; exactly one must be supplied.
- Typed resource managers with `get` / `list` / `create` / `update` / `delete`
  for user stories, bugs, tasks, features, epics, requests, test cases, times,
  releases, iterations, team iterations, projects, teams, users, entity
  states, priorities, severities, processes, workflows, entity types, terms,
  custom-field definitions, custom activities, custom rules, comments,
  assignments, team assignments, role efforts, roles, attachments, relations
  and relation types, plus the generic `entities` accessor for any other
  entity type.
- A server-declared write surface on every typed manager: each declares what
  its collection's `/meta` reports (`server_read_only`, or the per-operation
  `server_can_create` / `server_can_update` / `server_can_delete`), and an
  operation the server refuses raises `ReadOnlyViolation` in every mode
  before any request is sent - `relation_types`, `entity_types` and `terms`
  are read-only, `custom_rules` is update-only - with the generic `entities`
  accessor mirroring the same refusals by name.
- `list()` semantics: verbatim `where=` filters, `include=` field selection, a
  total `limit`, a per-request `page_size`, and pagination that follows the
  server's `Next` URL verbatim while refusing a `Next` that points at another
  host.
- Pydantic v2 models for every entity type, declaring the documented API
  fields of each with snake_case access. The six base-field PascalCase
  accessors (`Id`, `ResourceType`, `CreateDate`, `ModifyDate`, `CustomFields`,
  `Name`) are the only wire-named attributes: a declared field is reached by
  its snake_case name and its PascalCase name is not an attribute
  (`model_dump(by_alias=True)` gives the wire names). Undeclared API fields
  are preserved in `model_extra`, `CustomFields` parse on every entity, and
  TP's `/Date(ms±HHMM)/` wire format parses to timezone-aware datetimes.
- `scripts/check_model_coverage.py`: compares every model's declared fields
  against a live instance's `/meta`, with known deviations recorded in the
  script so only a new mismatch is reported.
- Name resolvers that never guess an Id: `priorities.resolve` (scoped by entity
  type), `roles.resolve`, `relation_types.resolve`, `severities.resolve`,
  `processes.resolve`, `entity_types.resolve` and `custom_activities.resolve`,
  raising `NotFoundError` or `AmbiguousMatchError`.
- `times.find_for_day` and `times.upsert`: a find-then-create/update keyed on
  assignable, user and day, with `dry_run` support.
- `attachments.download` and `attachments.upload` for TargetProcess's
  out-of-band file endpoints. `upload` returns the created record as
  `UploadedAttachment`, the typed form of the undocumented camelCase
  `{"items": [...]}` envelope `/UploadFile.ashx` answers with, so a caller
  need not re-list the entity's attachments to find what it just created.
- `scripts/live_smoke.py`: a read-only live smoke run over every read
  accessor, asserting the readonly refusal still fires. Not a CI gate - it
  needs a live instance and a token.
- Retry with exponential backoff (honouring `Retry-After`) on 429 and 5xx for
  safe methods only; writes are never retried automatically. Non-blocking
  async rate limiting via `easylimit`.
- A typed exception hierarchy under `TargetProcessError`.
- Observability: a `targetprocess` logger with a structured JSON formatter,
  credential scrubbing, and `X-Request-ID` correlation-ID propagation.
- `py.typed` marker; the package passes `mypy --strict`.
- Recorded write-path integration cassettes
  (`tests/integration/test_live_readwrite.py`): `create`/`update`/`delete`
  round trips for `UserStory` and `Request`, and `create_many`/`update_many`
  on `Task`, replayed offline like the read-only suite. They pin what
  TargetProcess actually answers a write with - a fully hydrated entity echo
  on both create and update rather than a bare Id, an advancing
  `EntityVersion`, a numeric field read back to show the update was applied
  and not merely accepted, a delete evidenced by a read-back that raises
  `NotFoundError`, and the `Items`-wrapped bulk envelope `RequestHandler.bulk`
  accepts alongside a bare array.
- Recorded write-path integration cassettes for the surfaces hung off a work
  item (`tests/integration/test_live_readwrite_surfaces.py`): `comments`,
  `assignments`, `team_assignments`, `role_efforts`, `relations` and
  `attachments`. Recording the `team_assignments` pair needs a team linked to
  the sandbox project for the duration of that run; replay needs no link.
- A tracked-file guard (`scripts/check_internal_refs.py`, run by pre-commit
  and CI) that fails on a reference into a private issue tracker or an agent
  session, so the published repository carries none.

### Security

- Recorded integration cassettes are sanitised at record time (token, every
  TargetProcess host - the instance and the vendor's own - free text and
  identity fields) and checked by an independent content scan on every test
  run.
- Log scrubbing redacts the `access_token` query parameter and `Authorization`
  header values from the library's own log records.

[Unreleased]: https://github.com/man8/targetprocess-py/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/man8/targetprocess-py/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/man8/targetprocess-py/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/man8/targetprocess-py/releases/tag/v0.1.0
