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

Requires [uv](https://docs.astral.sh/uv/). `.python-version` and
`.tool-versions` both pin the development interpreter (3.13); the library
itself supports 3.12 and 3.13 (`requires-python >=3.12` in `pyproject.toml`),
and CI runs the test suite on both.

```bash
git clone https://github.com/man8/targetprocess-py.git
cd targetprocess-py
uv sync --all-extras
uv run pre-commit install   # installs the pre-commit, commit-msg and pre-push hooks
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
| Commit message | `uv run pre-commit run --hook-stage commit-msg --commit-msg-filename <file>` (CI runs it over the pull request title) |
| Dependency vulnerabilities | `pip-audit` over the locked environment (CI) |
| Package build | `uv build` and `twine check` (CI) |

Every hook that names no stage — `ruff-check`, `ruff-format`, the three
repository checks (file size, debt markers, internal references) and the
upstream `pre-commit-hooks` set (large added files, YAML and TOML validity,
merge-conflict markers, private keys, end-of-file and trailing whitespace) —
runs at both the commit and the push stage. `mypy --strict src` is pinned to
the push stage alone, being too slow to gate every commit and meaningful only
over the whole package. Ruff and mypy run through `uv run`, so the hook
versions are exactly the ones pinned in `uv.lock`, with no second pin to
drift.

Also enforced:

- A 1000-line / 256 KiB ceiling per tracked file
  (`scripts/check_large_files.py`). `uv.lock` and the integration cassettes
  are exempt, as generated artefacts whose size is not a design decision.
- An issue reference on every debt marker (`scripts/check_todos.py`): a
  `TODO`, `FIXME`, `HACK` or `XXX` with no reference is debt nobody owns,
  since it never reaches a board. Markdown is not scanned — a marker in
  prose is documentation about markers, not debt in a code path.
- No internal references in tracked files (`scripts/check_internal_refs.py`)
  or in commit messages (`scripts/check_commit_message.py`).
- A cyclomatic-complexity ceiling of 10 (ruff `C901`).
- Copy-paste detection above 3% duplication over Python sources
  (`.jscpd.json`). Node-only tooling, so it runs in CI rather than requiring
  a Node toolchain on every dev machine.

The internal-references check matches a generic shape — an upper-case key of
two to six characters, a dash, and up to six digits — rather than a list of
keys, since publishing that list would leak the very thing the check exists to
keep out. Matching is case-sensitive: lower-cased, the same shape also matches
a locked dependency version and a GUID fragment. `EXCLUDED_PREFIXES` excuses
the public standards designations that share the shape. Prose is scanned
here, unlike the debt-marker check above, because the hook runs over every
tracked text file. `ALLOWED_PATHS` permits a file by path alone — an entry
exempts references only, so a session URL or trailer is refused there too —
and it lapses as soon as the file stops carrying a reference, which
`tests/test_internal_refs.py` asserts. The commit-message hook refuses the
same shape with the same exclusions.

Coverage is branch coverage over `src/`, gated at 90%. A change that drops
coverage below the gate is not mergeable; add tests with the change rather than
after it.

`.github/workflows/ci.yml` runs five job definitions — six job runs, since
`test` is a two-value matrix — on every push to `main` and every pull
request: `test` (`uv sync`, `ruff check`, `ruff format --check`,
`mypy --strict`, `pytest` with the coverage gate, over a Python 3.12/3.13
matrix with `UV_PYTHON` overriding the `.python-version` pin per leg);
`quality` (`pre-commit run --all-files` at both the `pre-commit` and
`pre-push` stages, which also proves the hook configuration itself still
works); `duplication` (jscpd); `audit` (`pip-audit` over `uv.lock` exported
with every extra and its hashes, failing the job on any known
vulnerability); and `build` (`uv build`, `twine check --strict`, and an
import of the built wheel from a clean environment).

`.github/workflows/release.yml` builds the distributions on a `v*` tag,
refuses a tag whose commit is not on `main` or whose name disagrees with the
wheel's version, and publishes to PyPI by trusted publishing (OIDC) under the
`pypi` GitHub environment. No token is stored; the environment's protection
rules are the manual gate on a publish.

One check runs outside CI, since it needs a live instance and a real token
that CI has neither of: `scripts/check_model_coverage.py` diffs each model's
declared aliases against its type's `/api/v1/{collection}/meta` and reports
coverage per model in both directions — a field TP declares that the model
does not, and a field the model declares that TP does not. It is GET-only;
`--fail-under` turns it into a gate for a caller who does have both a live
instance and a token. Three further conditions fail a run besides a coverage
shortfall: a declared field absent from `/meta`; a dead `EXCLUDED` or
`KNOWN_DEVIATIONS` entry — recorded to keep a decision visible, and stale as
soon as that decision changes; and a `/meta` body reporting no properties at
all, which is a failed measurement rather than full coverage. `--validate`
additionally fetches real records and parses them through each model — the
check `/meta` alone cannot make, since it says which properties exist and
not what TP puts in them — and a model whose sample cannot be fetched is
reported as not checked and fails the run.

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
    the token but nothing field-level, save the name of each custom field in a
    JSON request body (one entity, or every item of a bulk array), which is the
    tenant's configuration and is scrubbed to the placeholder as every `Name` in
    a response body is. So a request body is otherwise recorded as sent: a
    write-path test may only send text it invented, never a value copied off the
    live instance.
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
  the PascalCase accessors in `_base.py` (a per-file ignore in
  `pyproject.toml`; `models.py` is the re-export surface) and the
  `ReadOnlyViolation` name (a `noqa` at its declaration). Add a third only
  with the same kind of justification.
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
   `main`: write it as a Conventional Commits subject, exactly as below. CI
   checks the title with the same hooks that check a commit message.

## Commit messages

Commit messages follow the
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
specification, enforced at the commit-msg stage by the hooks
`pre-commit install` sets up and described for editor tooling in
[`.commitlintrc.json`](.commitlintrc.json).

Format: `<type>[optional scope]: <description>`

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`,
`ci`, `chore`, `revert`. A breaking change carries `!` after the type or scope,
or a `BREAKING CHANGE:` footer.

```text
feat(times): add find_for_day
fix: follow a relative Next link without dropping the query
docs: describe the write surface in USAGE.md
feat!: require an explicit mode on the client
```

- The type in lower case; the description in lower case or sentence case,
  never Title Case; imperative mood ("add", not "added"); no full stop; first
  line at most 72 characters.
- Where the change needs explaining, a body that says what changed and why,
  separated from the subject by a blank line.
- Reference an issue on this repository in a footer: `Fixes #123`. A key from
  any other tracker is refused by the commit-msg hook
  ([`scripts/check_commit_message.py`](scripts/check_commit_message.py)), for
  the same reason tracked files carry none.
- Attribution trailers naming a co-author, including an AI agent and the
  session that produced the change, are welcome: they say how the change was
  made.

## Releasing

A release is a pull request followed by a tag.

1. In a pull request, set `__version__` in `src/targetprocess/__init__.py`
   (the only version string; the build reads it). Move the `[Unreleased]`
   entries in `CHANGELOG.md` under a `## [X.Y.Z] - YYYY-MM-DD` heading dated
   the release day, and update the link references at its foot. When the minor
   version changes, update the supported-versions table in `SECURITY.md`. When
   the development status changes, update the classifier in `pyproject.toml`
   and the README's Development Status section.
2. Once it has merged, a maintainer creates a signed, annotated tag on that
   commit on `main` and pushes it:
   `git tag -s vX.Y.Z -m "targetprocess-py X.Y.Z" <commit>`, then
   `git push origin vX.Y.Z`.
3. `.github/workflows/release.yml` builds and checks the distributions, then
   waits for a maintainer to approve the `pypi` environment deployment. Once
   approved it publishes to PyPI and creates the GitHub Release from the
   version's CHANGELOG section.
4. Confirm the new version on PyPI and its GitHub Release.

## Reporting a vulnerability

See [SECURITY.md](SECURITY.md). Do not open a public issue for a suspected
vulnerability.

## Licence

By contributing you agree that your contribution is licensed under the
project's [MIT License](LICENSE).
