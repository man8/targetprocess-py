# targetprocess-py

[![CI](https://github.com/man8/targetprocess-py/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/man8/targetprocess-py/actions/workflows/ci.yml)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](https://github.com/man8/targetprocess-py/blob/main/LICENSE)
[![Python 3.12 | 3.13](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://github.com/man8/targetprocess-py/blob/main/pyproject.toml)

An async Python library for the TargetProcess v1 REST API with immutable safety modes and comprehensive error handling.

## Features

- **Broad Entity Coverage**: Typed resource managers for UserStory, Bug, Task, Feature, Epic, Request, TestCase, Time, Release, Iteration, TeamIteration, Project, Team, User, EntityState, Priority, Severity, Process, Workflow, EntityType, Term, CustomField, CustomActivity, CustomRule, Comment, Assignment, TeamAssignment, RoleEffort, Role, Attachment, Relation, and RelationType, plus a generic `entities` accessor for anything else
- **Immutable Safety Mode**: Readonly/readwrite modes frozen at initialization, enforced at both the resource and request-handler layers
- **Async-Only**: Built on `httpx`'s async client; there is no sync client
- **Type-Safe Models**: Pydantic v2 models for all entities, declaring the full value and reference field surface each type's `/meta` reports; snake_case field access throughout, and the 6 base Entity/NamedEntity fields (`Id`, `ResourceType`, `CreateDate`, `ModifyDate`, `CustomFields`, `Name`) also expose PascalCase property accessors matching the API
- **Resilient Requests**: Automatic retry with exponential backoff on HTTP 429 and 5xx responses (honouring `Retry-After` when present), plus non-blocking async rate limiting via `easylimit`
- **Real TP Semantics**: `access_token`-query-param auth (TP's actual token scheme; Basic auth as the header-based alternative), `where=` filter pass-through, and `Next`-URL pagination
- **Well Tested**: High test coverage with pytest, mypy strict mode, ruff linting, and a recorded VCR-cassette integration suite proving behaviour against a real TargetProcess instance

## Installation

```bash
pip install targetprocess-py
```

Or with [uv](https://github.com/astral-sh/uv), inside an existing uv project
(one with a `pyproject.toml`):

```bash
uv add targetprocess-py
```

For an environment-only install with no project, use `uv pip install targetprocess-py`.

## Quick Start

```python
import asyncio

from targetprocess import ClientMode, TargetProcessClient


async def main() -> None:
    async with TargetProcessClient(
        domain="example.tpondemand.com",
        token="your-api-token",  # sent as the access_token query param
        mode=ClientMode.READONLY,  # prevents accidental writes
    ) as client:
        # list() is an async generator - iterate it directly
        async for story in client.user_stories.list(
            where="(EntityState.Name eq 'Open')", limit=10
        ):
            print(f"{story.id}: {story.name}")


asyncio.run(main())
```

## Core Concepts

### Safety Modes

The client requires an immutable `mode` parameter at initialization:

- **`readonly`**: Blocks all write operations (create, update, delete) - perfect for reporting and analytics
- **`readwrite`**: Allows all operations - use when modifications are needed

```python
# Readonly client - safe for production automation
client = TargetProcessClient(..., mode="readonly")
await client.user_stories.create(...)  # Raises ReadOnlyViolation immediately

# Readwrite client - for authorized operations
client = TargetProcessClient(..., mode="readwrite")
await client.user_stories.update(id=123, state="Done")  # Works
```

The mode is frozen after initialization and cannot be changed, providing defense-in-depth for production workflows.

### Resource Managers

Access TargetProcess entities through typed resource managers:

```python
# Specific entity types
async for story in client.user_stories.list():
    ...
bug = await client.bugs.get(id=456)
task = await client.tasks.create(Name="Investigate outage")

# Generic entity access (when the type is only known at runtime)
entity = await client.entities.get("Bug", 789)  # Returns a NamedEntity
```

### Type-Safe Models

All entities use Pydantic models with snake_case field access. The six base
Entity/NamedEntity fields (`Id`, `ResourceType`, `CreateDate`, `ModifyDate`,
`CustomFields`, `Name`) also expose PascalCase property accessors matching the API;
every other field is snake_case-only:

```python
story = await client.user_stories.get(id=123)

# Base fields: both work
print(story.Id, story.id)              # Entity ID
print(story.Name, story.name)          # Entity name
print(story.CreateDate, story.create_date)  # Dates

# Everything else: snake_case only
print(story.entity_state)
```

Each model declares the **full** value and reference field surface its type's
`/api/v1/{collection}/meta` reports — 656 of 656 fields across the 32 modelled types,
measured against TP `2608.2.0.3147`. So the fields callers reach for are typed and
discoverable, not just tolerated:

```python
story = await client.user_stories.get(id=123)

print(story.creator.full_name)   # who raised it (a UserRef)
print(story.priority.name)       # entity-type-scoped Priority record
print(story.numeric_priority)    # global ordering rank (a float), not a Priority
print(story.time_spent, story.time_remain, story.effort_todo)
print(story.tags, story.units, story.forecast_end_date)
```

The class hierarchy mirrors TP's own, so a field TP defines once is declared once:
`Entity` → `NamedEntity` → `GeneralEntity` (TP's `General`) → `AssignableEntity`
(TP's `Assignable`). The six work-item types extend `AssignableEntity`; `Project`,
`Team`, `Release`, `Iteration`, `TeamIteration` and `TestCase` extend `GeneralEntity`;
the lookup, join and content types extend `Entity`/`NamedEntity` directly.

Two things stay outside that surface, both deliberately. TP's **collection**
properties (`Comments`, `Messages`, `Revisions`, …) are hydrated only via `include=`
and arrive as an `Items` envelope, so they remain undeclared and land in
`model_extra` — the exceptions being `CustomFields` and `AssignedUser`. And
`User.Password`, which TP marks unreadable, is left undeclared: a read payload
never carries it, so a dump of one never has a password-shaped attribute. It
can still be set through `users.update(id, Password=...)`.

[`scripts/check_model_coverage.py`](scripts/check_model_coverage.py) re-measures
coverage against a live instance, and with `--validate` also parses real records
through each model — the check `/meta` cannot make, since it says which properties
exist and not what TP puts in them. It is a dev-time tool, not a CI gate: it needs a
real token, which CI does not have.

Numeric fields TP computes carry no range constraint. A bound on a server-supplied
value fails the *whole entity* rather than the field, so one odd roll-up would abort
an entire `list()` page; TP documents no bounds to assert. Range checks belong on the
write side, where `times.upsert` already puts them.

## Usage

All examples below assume an open `client` (see [Quick Start](#quick-start)).
For the full walkthrough — basic operations, querying, error handling,
async-vs-sync, and safety-mode practice — see the [usage guide](docs/USAGE.md).
Runnable scripts live in [`examples/`](examples/).

### Resource managers

Each entity type is a property on the client, all sharing the same
`get` / `list` / `create` / `update` / `delete` surface, plus bulk
`create_many` / `update_many` (one `POST /{collection}/bulk` request for a
whole batch — one rate-limit slot instead of one per entity):

`user_stories`, `bugs`, `tasks`, `features`, `epics`, `requests`,
`test_cases`, `times`, `releases`, `iterations`, `projects`, `teams`, `users`,
`entity_states`, `priorities`, `comments`, `assignments`, `team_assignments`,
`role_efforts`, `roles`, `attachments`, `relations`, `relation_types`,
`team_iterations`, `custom_fields`, `severities`, `processes`, `workflows`,
`entity_types`, `terms`, `custom_activities`, `custom_rules` — plus
`entities`, the generic accessor that takes the entity type name as its first
argument and carries the full read-and-write surface for anything without a
typed manager, gated by the same safety mode as the typed resources.

The server bounds the write surface too. Each manager declares what its
collection's `/meta` reports (`CanCreate` / `CanUpdate` / `CanDelete`), and
an operation the server refuses raises `ReadOnlyViolation` in every mode,
before any request is sent: `relation_types`, `entity_types` and `terms` are
read-only on the server, and `custom_rules` is update-only (toggling
`IsEnabled`), so it refuses `create` and `delete`. The generic `entities`
accessor mirrors the same refusals by name.

Typed coverage is deliberately the common paths plus the lookup and
configuration collections; the long tail — the polymorphic bases, the people
and allocation collections, metadata and audit, and the work-item types not
yet modelled — stays on `entities` by design, and gains a typed manager on
demand. See [SPEC.md](SPEC.md) § *Typed versus generic coverage*.

### Filtering and field selection

`where=` is a TargetProcess filter expression, passed through verbatim (no
client-side rewriting); `include=` selects extra fields to hydrate:

```python
async for bug in client.bugs.list(
    where="(EntityState.IsFinal eq 'false')",
    include=["EntityState", "AssignedUser"],
    limit=50,
):
    state = bug.entity_state.name if bug.entity_state else "—"
    print(f"{bug.id}: {bug.name} [{state}]")
```

`list()` also passes TP's server-side sorting and payload-shaping parameters
through as typed keyword arguments — `order_by` / `order_by_desc`, `exclude`,
`result_include`, `append`, `innertake`, and an opt-in `skip` offset — see
the [usage guide](docs/USAGE.md#filtering-and-querying).

### Pagination

`list()` is an async iterator that fetches pages lazily. `limit` caps the
**total** number of items yielded across all pages; `page_size` is the
per-request page size (`take=`), independent of `limit`:

```python
# At most 200 items, fetched 50 per request
async for story in client.user_stories.list(limit=200, page_size=50):
    ...

# Unbounded: omit limit; pages are fetched as you iterate
async for story in client.user_stories.list():
    ...
```

`limit=0` yields nothing and makes no network request. Pagination follows the
server's `Next` URL verbatim (never a locally recomputed `skip`), so short or
irregular pages never silently drop or duplicate items.

### Error handling

Every library error subclasses `TargetProcessError`, so you can catch a
specific failure or the base class:

```python
from targetprocess import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    TargetProcessError,
)

try:
    bug = await client.bugs.get(id=123)
except NotFoundError:
    ...  # 404 — no such entity
except AuthenticationError:
    ...  # 401 — bad or expired credentials
except RateLimitError:
    ...  # 429 — persisted after the built-in retries
except TargetProcessError:
    ...  # any other library error
```

A `READONLY` client raises `ReadOnlyViolation` if a write is attempted — see
[Safety-mode best practices](docs/USAGE.md#safety-mode-best-practices).

429 and 5xx responses on safe methods (`get`/`list`) are retried automatically
with exponential backoff (honouring `Retry-After`); writes are never
auto-retried. See the [usage guide](docs/USAGE.md#error-handling) for the full
exception hierarchy and retry policy.

## Troubleshooting

| Symptom | Cause & fix |
| --- | --- |
| `ValueError: Provide exactly one of token or basic_auth` | Pass exactly one auth method to the client — a `token` **or** a `basic_auth=(user, pass)` tuple, never both or neither. |
| `AuthenticationError` (401) | The `access_token` / Basic credentials are wrong or expired. |
| `ReadOnlyViolation` on a write | The client is in `READONLY` mode. Construct it with `mode=ClientMode.READWRITE` for `create`/`update`/`delete`. |
| `AttributeError: mode is immutable …` | `mode` is frozen at construction — build a new client rather than reassigning it. |
| `ParseError` | The response body did not match the model (often an unexpected `include=` shape). The wrapped `pydantic.ValidationError` is in the exception message. |
| `NetworkError` vs `RateLimitError` | `NetworkError` means no HTTP response arrived (connection error, timeout, DNS); `RateLimitError` means a 429 persisted after retries. |
| Token appearing in logs | The `access_token` travels as a URL query parameter, so it can surface in server/proxy logs — do not enable httpx request-URL logging in production. |

## Architecture

Five-layer architecture for clean separation of concerns:

1. **Transport Layer**: HTTP communication (httpx), authentication, rate limiting (easylimit)
2. **Request Handler / Response Parser Layer**: Query construction, pagination, retry/backoff, and error mapping
3. **Resource Layer**: Entity-specific managers (UserStories, Bugs, Tasks, etc.)
4. **Model Layer**: Pydantic models for type safety and validation
5. **Client Layer**: Main entry point, safety mode enforcement, session management

See [SPEC.md](SPEC.md) for the full specification, including detailed architecture documentation.

## Development Status

**Current Status**: Alpha - core library complete

- ✅ Project structure and configuration
- ✅ Exception hierarchy
- ✅ Client safety modes (handler-layer + resource-layer enforcement)
- ✅ HTTP transport layer (access_token / Basic auth)
- ✅ API request/response handling (RequestHandler + ResponseParser), retry/backoff, rate limiting
- ✅ Entity models (42 model classes: the `Entity`/`NamedEntity`/`GeneralEntity`/`AssignableEntity` base chain, 6 nested shapes (`EntityRef`, `EntityTypeRef`, `UserRef`, `RefWithImportance`, `CustomFieldValue`, `CustomFieldConfig`), and 32 concrete entity types across the assignable, planning, organisational, workflow and configuration, join, supporting, and custom-field groups), each declaring its type's full `/meta` field surface
- ✅ Resource managers (typed + generic)
- ✅ Recorded integration test suite against a real TargetProcess instance

## Requirements

- Python 3.12+
- httpx >= 0.27.0
- pydantic >= 2.0.0
- easylimit >= 0.3.4

## Contributing

Contributions are welcome! Please see [SPEC.md](SPEC.md) for the current specification.

### Secrets management

The library and example scripts read all credentials from environment
variables — never from a committed file. The relevant variables are documented
in [`.env.example`](.env.example) (the committed template) and the
[examples README](examples/README.md#configuration):

| Variable | Purpose |
| --- | --- |
| `TP_DOMAIN` | TargetProcess instance domain |
| `TP_TOKEN` | API token (sent as the `access_token` query parameter) |
| `TP_WRITE_ALLOWED_PROJECT_IDS` | Project id allow-list for the write examples |

For local development, copy the template to `.env` (which is gitignored) and
export the values into your shell:

```bash
cp .env.example .env        # fill in real values
set -a && . ./.env && set +a  # export them for the current shell
```

`.gitignore` matches `.env`, suffixed variants such as `.env.local`, any
`*.env` file, and `.envrc`; `.env.example` is the only env-shaped file that is
tracked. CodeRabbit additionally treats a `.env` appearing in a diff as a
critical defect. Note that this is a review-time control, not a local hook —
nothing in `.pre-commit-config.yaml` blocks an env file that is force-added
past `.gitignore`.

For anything that runs outside a developer shell — CI, scheduled automation,
production — load these variables from a secrets manager (GitHub Actions
secrets, a vault, or your platform's equivalent) rather than from a `.env`
file. No real secret belongs in this repository: if a value ever needs to be
committed (e.g. an encrypted fixture), encrypt it with
[SOPS](https://github.com/getsops/sops) first and commit only the ciphertext.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/man8/targetprocess-py
cd targetprocess-py

# Install with dev dependencies
uv sync --all-extras

# Install the git hooks (lint + format on commit, types on push)
uv run pre-commit install

# Run tests
uv run pytest -q

# Run type checking
uv run mypy --strict src

# Run linting
uv run ruff check .
uv run ruff format --check .
```

### Quality gates

The hooks in [`.pre-commit-config.yaml`](.pre-commit-config.yaml) run the same checks CI runs, so a
failure surfaces before the push rather than minutes later in a CI log. Running `uv run pre-commit
run --all-files --hook-stage pre-commit` and then the same command with `--hook-stage pre-push`
reproduces the CI `quality` job exactly.

| Gate | Where it runs | Rule |
| --- | --- | --- |
| Lint & format | pre-commit, CI | `ruff check` (including pep8-naming) and `ruff format --check` |
| Types | pre-push, CI | `mypy --strict src` |
| Tests & coverage | CI | `pytest` with branch coverage over `src`, gated at ≥90% |
| Cyclomatic complexity | pre-commit, CI | ruff `C901`, `max-complexity = 10` |
| File size | pre-commit, CI | 1000 lines / 256 KiB per tracked file ([`scripts/check_large_files.py`](scripts/check_large_files.py)) |
| Debt markers | pre-commit, CI | `TODO`/`FIXME`/`HACK`/`XXX` must name an issue, e.g. `TODO(#123)` ([`scripts/check_todos.py`](scripts/check_todos.py)) |
| Internal references | pre-commit, CI | No tracker-style issue references or agent session URLs in tracked files ([`scripts/check_internal_refs.py`](scripts/check_internal_refs.py)) |
| Copy-paste | CI | jscpd, failing above 3% duplication ([`.jscpd.json`](.jscpd.json)) |

Naming follows PEP 8 as enforced by ruff's `N` rules, with two documented exceptions in
`pyproject.toml`: the PascalCase property accessors in `_base.py` mirror the wire format the
TargetProcess API returns, and `ReadOnlyViolation` keeps its published name rather than gaining an
`Error` suffix.

One check runs outside CI: [`scripts/check_model_coverage.py`](scripts/check_model_coverage.py)
diffs the declared model fields against a live instance's `/meta`, which needs a token CI does not
have. `tests/test_model_field_coverage.py` pins the same surface offline and does run in CI.

### Dependency updates

Dependency bumps are automated by Dependabot ([`.github/dependabot.yml`](.github/dependabot.yml)),
which opens weekly pull requests for three ecosystems:

- **`uv`** — regenerates `uv.lock` only (`versioning-strategy: lockfile-only`), so the lower bounds
  declared in `pyproject.toml` are never rewritten: the supported floor stays a deliberate decision
  while the versions CI resolves stay current. Test/lint/type tooling is grouped into one PR; runtime
  majors (`httpx`, `pydantic`, `easylimit`) arrive individually because they surface in this
  library's public API.
- **`github-actions`** — refreshes the commit-SHA pins in `.github/workflows/`, which are safe but
  never float on their own.
- **`pre-commit`** — refreshes the `rev:` pins in `.pre-commit-config.yaml`. The ruff and mypy hooks
  are not pinned there (they run via `uv run`), so the `uv` ecosystem already covers them.

Bumps are merged through the same gates as any other change (ruff, ruff-format, `mypy --strict`,
pytest at ≥90% coverage, the pre-commit hook suite, duplication detection, CodeQL, review), never
pushed directly to `main`.

## License

Copyright (c) 2025-2026 man 8 consulting (Louis Mandelstam). Released under the
MIT License - see [LICENSE](LICENSE) for details.

## Links

- **Usage guide**: [docs/USAGE.md](docs/USAGE.md)
- **Examples**: [examples/](examples/)
- **Specification**: [SPEC.md](SPEC.md)
- **TargetProcess API Docs**: [IBM TargetProcess v1 REST API](https://www.ibm.com/docs/en/targetprocess/tp-dev-hub/saas?topic=v1-getting-started)

## Motivation

Built to enable automation workflows against a production TargetProcess instance, and to serve as a foundation for:
- MCP server for TargetProcess integration
- Windmill workflow automation wrappers
- Reporting and analytics tools
- Bulk operations and data migrations

Designed as a high-quality open-source library following modern Python best practices.
