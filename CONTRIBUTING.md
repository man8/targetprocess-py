# Contributing to targetprocess-py

Thank you for considering a contribution. This document covers how the project
is developed and what a change needs before it can merge.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Report
unacceptable behaviour to louis@man8.com.

## Before you start

- [SPEC.md](SPEC.md) is the behavioural contract. A change that alters
  behaviour updates SPEC.md in the same pull request; the specification and the
  code are reviewed together.
- Open an issue before a large change so the design can be discussed first.
  Bug reports and feature requests have templates under
  `.github/ISSUE_TEMPLATE/`.
- The library is async-only, targets Python 3.12+, and keeps its runtime
  dependencies to `httpx`, `pydantic` and `easylimit`. A new runtime dependency
  needs a strong reason.

## Development setup

Requires [uv](https://docs.astral.sh/uv/). `.python-version` pins the
development interpreter (3.13); the library itself supports 3.12 and 3.13, and
CI runs the test suite on both.

```bash
git clone https://github.com/man8/targetprocess-py.git
cd targetprocess-py
uv sync --all-extras
uv run pre-commit install   # installs both the pre-commit and pre-push hooks
```

## Quality gates

Every gate below runs in CI on each pull request. The pre-commit hooks run the
lint, format, type and repository checks locally, so those failures surface
before the push rather than in a CI log; tests, the vulnerability audit and the
package build run in CI.

| Gate | Command |
| --- | --- |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format --check .` |
| Types | `uv run mypy --strict src` |
| Tests and coverage | `uv run pytest -q --cov=targetprocess --cov-report=term --cov-fail-under=90` |
| Hook suite, commit stage | `uv run pre-commit run --all-files --hook-stage pre-commit` |
| Hook suite, push stage | `uv run pre-commit run --all-files --hook-stage pre-push` |
| Dependency vulnerabilities | `pip-audit` over the locked environment (CI) |
| Package build | `uv build` and `twine check` (CI) |

Also enforced: a 1000-line / 256 KiB ceiling per tracked file
(`scripts/check_large_files.py`), issue references on debt markers
(`scripts/check_todos.py`), no internal references in tracked files
(`scripts/check_internal_refs.py`), a cyclomatic-complexity ceiling of 10 (ruff
`C901`), and copy-paste detection above 3% (`.jscpd.json`, CI only).

Coverage is branch coverage over `src/`, gated at 90%. A change that drops
coverage below the gate is not mergeable; add tests with the change rather than
after it.

## Tests

- Unit tests live in `tests/` (one file per model, resource or component) and
  run against `httpx.MockTransport` or mocked request handlers: no network, no
  credentials.
- Test doubles are constrained to a real interface: `Mock(spec=...)` /
  `MagicMock(spec=...)`, and `patch(..., autospec=True)`. An unspecced double
  accepts any attribute and hides exactly the interface drift a test exists to
  catch. For shapes that spec poorly, use a real stub dict instead of a mock.
- `tests/integration/` replays recorded VCR cassettes offline; it needs no
  network and no credentials. Re-recording runs against a live TargetProcess
  instance and is a maintainer action (`ALLOW_PROD_RECORDING=1`): contributors
  do not re-record, and a pull request must not hand-edit a committed cassette.
- **Delete the target cassette before re-recording it.** `ALLOW_PROD_RECORDING=1`
  selects vcrpy's `once` mode, which records only when no cassette exists —
  over an existing one it silently replays instead. The run is green either
  way, so nothing distinguishes "re-recorded" from "replayed the file you
  meant to replace", and on the write path that green run also means no
  entities were created, which then makes the residue sweep below pass for
  the wrong reason. `--record-mode=rewrite` does not rescue this: the
  suite's `vcr_config` pins `record_mode`, and `pytest-recording` lets the
  config win. So:

  ```bash
  rm tests/integration/cassettes/<module>/<test_name>.yaml
  ALLOW_PROD_RECORDING=1 uv run pytest tests/integration/<module>.py::<test_name>
  ```

  Deleting only the cassettes you intend to replace keeps the rest untouched.
- Write-path cassettes (`tests/integration/test_live_readwrite.py` and
  `tests/integration/test_live_readwrite_surfaces.py`) record
  `create`/`update`/`delete` against the live instance, so re-recording them
  carries three rules on top of the above:
  - **Sandbox project only.** Every entity is created in the throwaway project
    that module's `_SANDBOX_PROJECT_ID` names, never in a real backlog, and a
    test only ever touches an entity it created itself.
  - **The test deletes what it created**, in a `finally` — and that delete *is*
    the recorded `delete` interaction, which is why cleanup belongs in the test
    body rather than a fixture teardown a later refactor could move outside the
    cassette.
  - **Everything sent is synthetic.** `_scrub_request` neutralises the host and
    the token but nothing field-level, so a request body is recorded as sent:
    a write-path test may only send text it invented, never a value copied off
    the live instance.
  - **Org-level state is read, never written.** Where a surface needs an
    existing Role, Team, RelationType or project membership, the test reads it
    live and uses it. Creating one would be a write outside the sandbox.
  - **`team_assignments` needs a team linked to the sandbox at record time.**
    TargetProcess refuses a `TeamAssignment` unless the Team is assigned to the
    card's project, and the sandbox carries no such link in its steady state —
    so re-recording `test_team_assignment_create_and_delete` means linking a
    team to the sandbox project for the duration of that run and unlinking it
    afterwards. The link is instance configuration rather than a throwaway
    record, so it is made by hand, and the test reads the team back out of the
    project's own `TeamProject` row rather than naming one. Every other run
    replays the cassette offline and needs no link.
- After a write-path recording, sweep the sandbox project for the module's
  `_NAME_PREFIX` — the string its entities are actually named with, which is a
  module constant rather than the reference of whichever change re-recorded a
  cassette — across each entity type the run touched, and confirm it is empty
  before committing. Prove the sweep can
  see a record first — plant one, find it, delete it — because an empty result
  from a filter nobody has tested is indistinguishable from a filter that
  matches nothing. Residue that cannot be deleted is a blocker, not a tidy-up.
- `scripts/live_smoke.py` exercises every read accessor once against a live
  instance in `READONLY` mode, ending on an assertion that a write is still
  refused. It is the check a cassette cannot make - whether the client still
  parses what TargetProcess sends *now*, rather than what it sent on the day
  of a recording - so run it by hand when a change touches parsing, when
  adopting a new instance, or before a release. It reads `TP_API_TOKEN` and
  `TP_BASE_URL` from the environment or `~/.config/targetprocess/.env`, has
  no default host, and exits non-zero if any accessor fails. Its output is
  identifiers and counts only, so it can be pasted into an issue unedited:
  the instance's tenant label is masked, and a failed check reports its
  exception type without the message, because a TargetProcess error quotes
  the user, project or card it is about. It is deliberately **not** a CI gate: CI has
  neither a live instance nor a token. Run it with
  `uv run python scripts/live_smoke.py`.
- Cassette redaction policy: the record-time hooks in
  `tests/integration/conftest.py` (see its module docstring) neutralise the
  instance host, the token, and free-text and identity fields before a
  cassette is written; `tests/test_cassette_guard.py` independently scans
  every committed cassette on every run. A cassette carrying a real host,
  token, name or login is a blocking defect, not a nit.

  Entity Ids are the deliberate exception: they are recorded as they came off
  the wire because with every name, login, title and hostname already a
  placeholder an Id identifies nothing on its own, while a rewritten one would
  reduce a filter or pagination assertion to comparing an invented value
  with itself.
  `docs/testing.md` and the `tests/integration/cassettes/**` instruction in
  `.coderabbit.yaml` state the same rule, so a review does not re-litigate it.

## Style

- Ruff enforces PEP 8, pep8-naming, Google-convention docstrings on the public
  API, and the complexity ceiling. There are two documented naming exceptions:
  the PascalCase accessors in `models.py` (a per-file ignore in
  `pyproject.toml`) and the `ReadOnlyViolation` name (a `noqa` at its
  declaration). Add a third only with the same kind of justification.
- Prose (docs, comments, docstrings) uses British English, and identifiers
  follow suit where a spelling choice exists. Field names that mirror the
  TargetProcess wire format keep TP's spelling and casing.
- Every public function, method and class carries a docstring.
- A `TODO`, `FIXME`, `HACK` or `XXX` in code names the issue that tracks it,
  e.g. `TODO(#123): ...`.
- Tracked files name no issue in a private tracker and no agent session, since
  neither resolves for a reader of the published repository: keep the
  rationale in the file as prose and let the reference live in the commit
  message, where `git blame` still reaches it
  ([`scripts/check_internal_refs.py`](scripts/check_internal_refs.py)).

## Pull requests

1. Branch from `main`.
2. Make the change, with its tests and any SPEC.md or docs update in the same
   pull request.
3. Run the gates above.
4. Open the pull request against `main`. The template's checklist must be
   fully ticked before merge; keep the description to what the change does and
   why.
5. Pull requests are squash-merged, so the title becomes the commit message on
   `main`: write it as an imperative summary of the change.

Commit messages use an imperative subject line and, where the change needs
explaining, a body that says what changed and why.

## Reporting a vulnerability

See [SECURITY.md](SECURITY.md). Do not open a public issue for a suspected
vulnerability.

## Licence

By contributing you agree that your contribution is licensed under the
project's [MIT License](LICENSE).
