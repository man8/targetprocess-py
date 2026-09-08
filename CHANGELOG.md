# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Initial development towards the first public release, `0.1.0`.

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

[Unreleased]: https://github.com/man8/targetprocess-py/commits/main
