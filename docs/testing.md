# Testing approach

How targetprocess-py is tested, and the rules a recorded cassette is made
under. Split out of [SPEC.md](../SPEC.md), which carries the behavioural
contract itself and links here; `CONTRIBUTING.md` § Tests carries the
operational recipe for running and re-recording.

- **Unit tests** (`tests/`, one file per model/resource/component) exercise
  every layer against mocked transports (`httpx.MockTransport`) or mocked
  request handlers - no network access, no cassettes.
- **Recorded integration tests** (`tests/integration/`) exercise the real
  client against a real TargetProcess instance. Cassettes are recorded once
  with `ALLOW_PROD_RECORDING=1` and committed; every other run replays them
  offline (`record_mode="none"`) with no network access and no real
  credentials required. Three modules, each with its own cassette directory
  so re-recording one never disturbs another: `test_live_readonly.py`
  (list/get), `test_live_readwrite.py` (create/update/delete and the bulk
  pair on the entities that carry work) and
  `test_live_readwrite_surfaces.py` (the same write path on the surfaces
  hung off them - comments, assignments, team assignments, role efforts,
  relations and the file-transfer pair).
- **Write-path recording rules** (`test_live_readwrite.py` and
  `test_live_readwrite_surfaces.py`): the only modules in the integration
  suite that build a `READWRITE` client, and so the only places in the
  repository that send a write to a real instance (the unit suite builds one
  against a mock transport). Every entity is created in a throwaway sandbox
  project fixed by a module constant, and each test deletes what it created
  in a `finally` — the delete being the recorded `delete` interaction, not
  teardown bookkeeping. `_scrub_request` neutralises only the host and
  token, so a request body is recorded as sent and may carry nothing but
  synthetic text; created entities are named with the module's
  `_NAME_PREFIX` constant, and the sandbox is swept for that string against a
  planted positive control before the cassettes are committed (CONTRIBUTING.md
  § Tests).

  Assertions there are structural, since the scrubber replaces the
  `Name`/`Description` a write sent before the response reaches disk. What
  evidences a write is the echoed `Id`/`ResourceType`, the `Project` or
  `UserStory` reference requested, and `EntityVersion`, which TP advances on
  every accepted change (`ModifyDate` cannot serve, being recorded to the
  second, so a create and an update moments later share one). `EntityVersion`
  shows only *acceptance*, so each update also sends a numeric `Effort` and
  reads it back — a number is recorded verbatim, making it the one value a
  test can prove TP applied. A delete is evidenced by a read-back raising
  `NotFoundError`, never its status alone; its `{"ResourceType", "Id"}` body
  is recorded but unasserted, `RequestHandler.delete` discarding it. Two
  undocumented shapes are pinned: create and update each echo a fully
  hydrated entity rather than a bare Id, and the bulk endpoint wraps its
  array as `Items`.
- **Cassette sanitisation at record time**: `filter_query_parameters`
  redacts the `access_token` value; `filter_headers` redacts the
  `authorization`, `proxy-authorization`, `cookie` and `cookie2` request
  headers (vcrpy applies it to requests only); `_scrub_response` drops the
  cookie family and `Content-Security-Policy` from recorded responses
  outright (a browser policy naming every third-party origin the vendor's
  UI uses, exercised by nothing in a client fixture); `_scrub_request` and
  `_scrub_response` neutralise every TP host that remains - the real tenant
  domain and the vendor's own infrastructure, CDN and corporate hosts -
  onto a placeholder host in the request URI and headers and in any
  response body/header that echoes it back (a `Location`, a pagination
  link); `_scrub_response` additionally strips free-text and PII-bearing
  fields (`Name`, `Description`, `FirstName`, `LastName`, `FullName`,
  `Login`, `Tags`) and drops `CustomFields` entirely, replacing text values
  with `Sanitised <Field>` placeholders. Those field names are matched
  **case-insensitively**, which is load-bearing rather than lenient: the JSON
  entity API answers in PascalCase, but `/UploadFile.ashx` - the multipart
  file endpoint outside `/api/v1` - answers in camelCase, so an exact-case
  match would recognise none of the identity fields in an upload response.
  `UniqueFileName` is in the set for the same reason its `Name` is: TP
  derives the stored filename from the one the upload sent.

  Structural fields — entity `Id`, `ResourceType`, dates, numeric/boolean
  fields, the `Items`/`Next`/`Prev` envelope — are recorded as they came off
  the wire so cassettes still exercise real parsing, pagination and filter
  behaviour. A bare numeric Id is deliberately **not** redacted, whether a
  real entity Id or one of the product-seeded lookup constants every TP
  tenant shares (Priority 1–5, EntityType 4): with every name, login, title,
  text and hostname already a placeholder, an Id on its own identifies
  nothing, while a rewritten one would reduce a filter assertion to comparing
  an invented value with itself (`test_priorities_scoped_to_an_entity_type`
  reads `EntityType.Id` as the only surviving evidence that the `where=`
  filter narrowed the result). The `.coderabbit.yaml` `path_instruction` for
  `tests/integration/cassettes/**` states the same rule, so a review does not
  re-litigate it. Dates are retained deliberately and not merely by omission:
  the recorded `Time.Date` values are live evidence of what TP actually
  stores for a `Time` entity, documented under *TargetProcess API Facts*,
  which `times.find_for_day` is built around.

  Both hooks run again on replay — vcrpy re-runs
  `before_record_request`/`before_record_response` when *loading* a
  cassette, not only when writing one — so they must be stable over an
  already-sanitised interaction, and `tests/test_cassette_sanitiser.py`
  asserts that over every committed cassette: the request and the response
  body come back byte-for-byte as recorded, and a second pass over the whole
  interaction changes nothing. A hook that rewrote a recorded request or
  body on load would corrupt replay on every offline run.
- **Write-path rules the second module is the first to need.** Org-level Ids
  - a Role, a RelationType, a project membership - are *read* live and used,
  never created: they are instance-wide state the suite does not own. And
  every read inside a write-path test is scoped by a `where=` to the entity
  the test just created, because an unfiltered `attachments.list()` would
  record a real customer's files into a committed fixture. Lookup members are
  selected by lowest Id rather than by name, which is load-bearing rather
  than tidy: the scrubber rewrites every `Name` before a cassette reaches
  disk, so a `resolve("...")` recorded here would find nothing on replay.
- **What TP refuses, and what that costs the suite.** An `Assignment` is
  rejected unless its user is a member of the card's project, so the user and
  role come from the sandbox project's own `ProjectMember` rows. A
  `TeamAssignment` is rejected unless the *Team* is assigned to the project,
  and the sandbox carries no such link in its steady state - so recording
  `test_team_assignment_create_and_delete` needs a team linked to the sandbox
  project for the duration of that run, made and removed by hand because the
  link is instance configuration this suite does not own. The test reads the
  team back out of the project's own `TeamProject` row rather than naming one,
  and every other run replays the cassette offline and needs no link.
- **Live smoke** (`scripts/live_smoke.py`): every read accessor exercised once
  against a live instance, in `READONLY` mode, ending on an assertion that a
  write is still refused. It answers the question a cassette cannot - whether
  the client still parses what TP sends *now*, rather than what it sent on
  the day of a recording. Not a CI gate (it needs a live instance and a real
  token) and never invoked by one; see CONTRIBUTING.md § Tests.
- **Cassette guard** (`tests/test_cassette_guard.py`): an independent,
  content-based regex scan of every committed cassette, run as a normal
  unit test on every CI run - not an honour-system marker. It catches a
  regression in the record-time sanitisation above by failing if any
  cassette contains an unredacted `access_token` value, an unredacted
  `authorization:` header, a loose base64-shaped token-like string, or the
  real client domain.
