"""Fixtures for the recorded integration suite.

Cassettes are recorded once against live TargetProcess with
``ALLOW_PROD_RECORDING=1``; every other run replays them offline
(``record_mode="none"``) with no network access and no real token required.
``test_live_readonly.py`` records list/get calls; ``test_live_readwrite.py``
records create/update/delete, confined to a throwaway sandbox project and
deleting every entity it creates (see its module docstring).

The client sends its token as an ``access_token`` query parameter (see
``targetprocess.transport._QueryTokenAuth``), so ``filter_query_parameters``
is the load-bearing sanitisation here — it substitutes ``REDACTED`` for the
token both when a cassette is written *and* when an incoming request is
matched against one already on disk (vcrpy runs the same
``before_record_request`` filter chain on both paths - see
``vcr.cassette.Cassette._responses``/``append``), so replay matching works
without a custom matcher. ``filter_headers`` covers the Basic-auth
alternative path as belt-and-braces even though this suite only exercises
token auth.

Recording hits a real customer's live TP backlog, so response *bodies* carry
real story/comment text, real employee names, and real custom-field values
(e.g. internal ticket links) - none of which belong in a committed fixture.
``_scrub_response`` strips all of that via ``before_record_response`` before
a cassette is ever written to disk (see its docstring for exactly what
survives).

The real customer's domain and the real token are client-identifying values
that can surface in *any* part of an interaction, not just the places vcrpy's
built-in filters reach. Two complementary controls neutralise them, and both
run over every carrier:

- ``_sensitive_replacements`` is a registry of "real value -> placeholder"
  pairs built from what this session knows: the configured domain and the
  token. It is exact-match, and it is the only thing that can catch the
  token, which has no recognisable shape.
- ``_TP_HOST_PATTERN`` matches any TP host by *shape* - a tenant host, or
  one of the vendor's own infrastructure, CDN and corporate hosts - and
  rewrites it to the placeholder. The registry only knows the hosts this session configured
  or observed, so a sibling tenant host the server echoes back — a
  region-routing ``Location``, a cross-tenant link in a body — would slip
  past it, as would the same host in a different case, and so would one of
  the vendor's own hosts. Matching the shape closes all of them.

The carriers, in full: the request URI, request headers (the ``Host`` header
in particular - rewriting only the URI leaves the real domain sitting in
``headers.host``), the request body (write-path payloads), response headers
(e.g. a ``Location`` echoing the domain back), and the response body (e.g.
``Next``/``Prev`` pagination links). Response headers are worth calling out:
``filter_headers`` is a *request*-only filter in vcrpy, so ``Set-Cookie`` on
the response is dropped here instead - as is ``Content-Security-Policy``,
which is not scrubbed but removed (``_DROPPED_HEADER_MARKERS``).

``_resolve_live_credentials`` never resolves the real domain from the
environment unless ``ALLOW_PROD_RECORDING`` is set, so an offline replay run
is deterministic even on a machine with a real
``~/.config/targetprocess/.env`` present - the host is part of vcrpy's
default request matcher, so the domain used to build requests must always
equal the one baked into the cassettes.

Entity ``Id`` values are structural and are recorded as they came off the
wire, alongside ``ResourceType``, dates, numeric/boolean fields and the
``Items``/``Next``/``Prev`` envelope: with every name, login, title, text and
hostname already a placeholder, a bare numeric Id identifies nothing on its
own, while a rewritten one would reduce a filter assertion to comparing an
invented value with itself (``test_priorities_scoped_to_an_entity_type``
reads ``EntityType.Id`` as the only surviving evidence that the ``where=``
filter narrowed the result). The product-seeded lookup constants every TP
tenant shares - Priority 1-5, EntityType 4 - are Ids of exactly this kind.
``.coderabbit.yaml`` states the same rule for the review bot.

Both hooks run again on replay, so they must be stable over an
already-sanitised interaction, and ``tests/test_cassette_sanitiser.py``
asserts that over every committed cassette: ``Cassette.load()`` calls
``append()`` - and so both hooks - for every interaction *already on disk*,
for every cassette, on every replay run (see ``vcr.cassette.Cassette._load``),
not only while genuinely recording. A hook that rewrote a request or a
response body on that pass would corrupt every cassette in memory on every
offline run - a response Id re-used to build a later request would no longer
match the interaction recorded for it - so on replay both come back
byte-for-byte as recorded, and a second pass over the whole interaction
changes nothing. The domain and token scrubbers meet this by construction:
on replay ``_resolve_live_credentials`` resolves to the placeholders, so the
exact-match registry is empty, and the shape-matched pass either finds only
the placeholder host or neutralises a vendor TP host in a response header
identically on every load - as ``_resync_response_content_length`` corrects
a pre-scrub ``Content-Length`` identically on every load. Those two header
normalisations are the most a committed response may change on load.
"""

import functools
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import pytest

# Neutral stand-in for the real customer domain the cassettes were recorded
# against. Used both as the offline-replay fallback (see
# ``_resolve_live_credentials``) and as the record-time rewrite target (see
# ``_sensitive_replacements``).
_PLACEHOLDER_DOMAIN = "example.tpondemand.com"

# Stand-in for any real secret (token, credential) in a recorded interaction.
# Matches the value vcrpy's ``filter_query_parameters`` substitutes for the
# ``access_token`` query parameter, so the two paths agree.
_REDACTED = "REDACTED"

# Any TargetProcess host, in either str or bytes form (a response body arrives
# as bytes): a tenant host whatever its tenant or region prefix
# (``<tenant>.tpondemand.com``, ``<tenant>.<region>.tpondemand.com``), and the
# vendor's own hosts a response may echo in a header or a body - its
# infrastructure and CDN (``<name>.tpondemand.net``, ``*.cdntpondemand.com``)
# and its corporate domains (``<name>.targetprocess.com``, ``tauboard.com``) -
# a wildcard label included. None of those is the tenant, but every one says
# which vendor the recording was made against, which a public fixture has no
# business carrying. Case-insensitive because the casing of an echoed-back
# host is the server's to choose, not ours. See the module docstring for why
# shape-matching complements the exact-match registry rather than replacing
# it. A module-level literal: the pattern is fixed, never built from input.
_TP_HOST_RE = (
    r"(?:[A-Za-z0-9*-]+\.)*"
    r"(?:(?:cdn)?tpondemand\.(?:com|net)|targetprocess\.com|tauboard\.com)"
)
_TP_HOST_PATTERN = re.compile(_TP_HOST_RE, re.IGNORECASE)
_TP_HOST_PATTERN_BYTES = re.compile(_TP_HOST_RE.encode("ascii"), re.IGNORECASE)

# Headers dropped outright at record time, matched by substring on the
# lowercased name rather than by exact name. Two families:
#
# - ``cookie``: a server-set session cookie carries a live credential, and
#   ``filter_headers`` only runs over *requests* in vcrpy (see
#   ``VCR._build_before_record_request``), so ``Set-Cookie`` would otherwise
#   land in the cassette verbatim. The family is open-ended (``Set-Cookie``,
#   ``Set-Cookie2``, whatever a proxy adds), so an enumeration would fail
#   silently on the first variant nobody listed.
# - ``content-security-policy``: a browser policy listing every third-party
#   origin the vendor's web UI talks to - SaaS analytics, identity providers,
#   support widgets. Nothing a client-library fixture exercises, and a host
#   list that never converges under scrubbing, so it goes rather than being
#   rewritten (the substring also catches ``-Report-Only``).
#
# ``tests/test_cassette_guard.py`` matches the same shapes independently.
_DROPPED_HEADER_MARKERS: tuple[str, ...] = ("cookie", "content-security-policy")


def _is_dropped_header(name: str) -> bool:
    """Whether a header is one the record hooks remove rather than scrub."""
    lowered = name.lower()
    return any(marker in lowered for marker in _DROPPED_HEADER_MARKERS)


# Field names that carry human-authored free text or personally-identifying
# data anywhere they appear in a TP payload (story/comment titles and bodies,
# assignee/owner/commenter identity, freeform tags). Every other field - Id,
# ResourceType, dates, numeric/boolean fields, and the Items/Next/Prev
# collection envelope - is left untouched so the recorded shape still
# exercises real parsing, pagination and filter logic (see the module
# docstring on why a bare Id is not a leak).
#
# ``UniqueFileName`` is TP's stored name for an uploaded file. It is derived
# from the filename the upload sent, so it carries whatever ``Name`` carries
# and belongs under the same rule - leaving it out would scrub a document's
# name in one field and record it verbatim in the next.
#
# Matched case-insensitively, which is load-bearing rather than lenient: the
# JSON entity API answers in PascalCase, but ``/UploadFile.ashx`` - the
# multipart file endpoint outside ``/api/v1`` - answers in **camelCase**
# (``firstName``, ``login``, ``fullName``), so an exact-case match recognises
# none of the identity fields in an upload response. Any endpoint TP serves
# off the application root may answer in its own casing, so the match is on
# the field's identity, not on the casing one endpoint happens to use.
_REDACT_TEXT_KEYS = {
    "Name",
    "Description",
    "FirstName",
    "LastName",
    "FullName",
    "Login",
    "Tags",
    "UniqueFileName",
}
_REDACT_TEXT_KEYS_FOLDED = {key.lower() for key in _REDACT_TEXT_KEYS}

# The org-specific custom-field list, dropped wholesale rather than scrubbed
# per field. Folded for the same reason as the set above.
_DROPPED_BODY_KEY = "customfields"

# Populated by ``_scrub_request`` with the real host it just rewrote, so
# ``_scrub_response`` can scrub the same string out of the paired response
# (e.g. pagination links, CSP/Location headers). Safe as simple shared state:
# vcrpy's ``Cassette.append`` calls ``before_record_request`` then
# ``before_record_response`` for one interaction back-to-back with no
# ``await`` in between (see ``vcr.cassette.Cassette.append``), so there is no
# interleaving even under asyncio concurrency.
_last_request_host: dict[str, str] = {}


def _sensitive_replacements() -> list[tuple[str, str]]:
    """Every real value that must never reach a cassette, paired with its placeholder.

    Two sources, because neither alone is sufficient: the configured
    credentials (which carry the token - already stripped from the request
    query string by ``filter_query_parameters`` before the hooks run, but
    still able to surface in a response body or header) and the host actually
    observed on the wire (which covers a redirect or a differently-configured
    base URL). Offline replay resolves to the placeholders, so this is empty
    and the exact-match pass becomes a no-op - ``_TP_HOST_PATTERN`` still
    runs, but on an already-placeholder host it changes nothing.

    A configured domain carrying a non-default port is registered both with
    and without it, longest first, because httpx omits the port from the
    ``Host`` header when it is the scheme default and includes it otherwise.
    """
    domain, token = _resolve_live_credentials()
    pairs: list[tuple[str, str]] = []
    for host in (domain, domain.split(":")[0], _last_request_host.get("host")):
        if host and host != _PLACEHOLDER_DOMAIN and (host, _PLACEHOLDER_DOMAIN) not in pairs:
            pairs.append((host, _PLACEHOLDER_DOMAIN))
    if token and token != _REDACTED:
        pairs.append((token, _REDACTED))
    return pairs


def _neutralise_tp_hosts(value: str) -> str:
    """Rewrite every TP tenant host to the placeholder, leaving the placeholder itself alone."""
    return _TP_HOST_PATTERN.sub(
        lambda match: (
            match.group(0) if match.group(0).lower() == _PLACEHOLDER_DOMAIN else _PLACEHOLDER_DOMAIN
        ),
        value,
    )


def _neutralise_tp_hosts_bytes(value: bytes) -> bytes:
    """Bytes counterpart of ``_neutralise_tp_hosts``.

    Applied on the raw body rather than a decoded copy so a non-UTF-8 payload
    (an attachment download, say) is still scrubbed instead of raising.
    """
    placeholder = _PLACEHOLDER_DOMAIN.encode("ascii")
    return _TP_HOST_PATTERN_BYTES.sub(
        lambda match: match.group(0) if match.group(0).lower() == placeholder else placeholder,
        value,
    )


def _scrub_text(value: str, replacements: list[tuple[str, str]]) -> str:
    """Apply the exact-match registry, then the shape-matched TP-host catch-all."""
    for real, placeholder in replacements:
        value = value.replace(real, placeholder)
    return _neutralise_tp_hosts(value)


def _scrub_bytes(value: bytes, replacements: list[tuple[str, str]]) -> bytes:
    for real, placeholder in replacements:
        value = value.replace(real.encode("utf-8"), placeholder.encode("utf-8"))
    return _neutralise_tp_hosts_bytes(value)


def _body_length(body: Any) -> int:
    return len(body if isinstance(body, bytes) else str(body).encode("utf-8"))


def _resync_request_content_length(request: Any) -> None:
    """Keep a request's ``Content-Length`` consistent with a body the scrubber resized.

    Purely for the benefit of a human eyeballing a cassette diff - vcrpy
    replays the stored body regardless - but an interaction whose declared
    length disagrees with its body reads as corruption and wastes the
    reader's time.
    """
    length = _body_length(request.body)
    request.headers = {
        key: (str(length) if key.lower() == "content-length" else value)
        for key, value in request.headers.items()
    }


def _resync_response_content_length(response: dict[str, Any]) -> None:
    """Response counterpart of ``_resync_request_content_length``.

    The response body is rewritten twice over - once by the scrubbers, then
    again by ``json.dumps`` re-serialising the parsed payload - so a recorded
    ``Content-Length`` is essentially never still correct. Header values are
    lists here, not scalars, because that is vcrpy's response serialisation.
    """
    body = (response.get("body") or {}).get("string")
    if body is None:
        return
    length = str(_body_length(body))
    headers: dict[str, Any] = response.get("headers") or {}
    for key in headers:
        if key.lower() == "content-length":
            headers[key] = [length]


def _scrub_request(request: Any) -> Any:
    """VCR ``before_record_request`` hook: strip real host and credentials from the request.

    Runs on both the record path and the replay-matching path (see the
    module docstring's note on ``filter_query_parameters`` running the same
    way). Rewriting unconditionally to ``_PLACEHOLDER_DOMAIN`` is a no-op
    when the request is already on it (offline replay - ``live_credentials``
    resolves there directly without touching the environment) and
    neutralises the real customer domain when recording against production,
    so the recorded cassette never carries it in the first place.

    The URI is only the first carrier: httpx also sends the domain as a
    ``Host`` header (and would send it in ``Origin``/``Referer``, or in a
    write-path body that embeds an entity URL), so the scrubbers are applied
    across headers and body as well - rewriting the URI alone leaves the real
    domain in plain sight one line above it in the cassette.

    Cookie-carrying request headers are dropped outright rather than scrubbed:
    a session credential is not made safe by neutralising a domain inside it.
    ``filter_headers`` already removes the ones it names, so this is the
    backstop for any variant it does not - matched by shape, like the response
    side, so a new one is covered by default.
    """
    host = request.host
    if host:
        _last_request_host["host"] = host
        if host != _PLACEHOLDER_DOMAIN:
            parsed = urlparse(request.uri)
            netloc = (
                _PLACEHOLDER_DOMAIN
                if parsed.port is None
                else f"{_PLACEHOLDER_DOMAIN}:{parsed.port}"
            )
            request.uri = urlunparse(parsed._replace(netloc=netloc))

    replacements = _sensitive_replacements()
    request.uri = _scrub_text(request.uri, replacements)
    request.headers = {
        key: _scrub_text(value, replacements) if isinstance(value, str) else value
        for key, value in request.headers.items()
        if not _is_dropped_header(key)
    }

    original_body = request.body
    if isinstance(original_body, bytes):
        request.body = _scrub_bytes(original_body, replacements)
    elif isinstance(original_body, str):
        request.body = _scrub_text(original_body, replacements)
    elif original_body is not None:
        # A file-like or iterator body would serialise as an opaque pickled
        # blob that no scrubber here has read and no committed-cassette guard
        # regex can see into. vcrpy's httpx stubs materialise every request
        # stream to bytes before building the Request, so this is unreachable
        # today - which is exactly why it must fail loudly if that ever
        # changes, rather than silently recording an unscrubbed payload.
        raise TypeError(
            f"Cannot scrub request body of type {type(original_body).__name__}; "
            "recording aborted rather than risk writing an unsanitised cassette."
        )
    if request.body != original_body:
        _resync_request_content_length(request)
    return request


def _scrub(value: Any) -> Any:
    """Recursively replace free-text/identity field values with placeholders."""
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, v in value.items():
            folded = key.lower()
            if folded == _DROPPED_BODY_KEY:
                # Org-specific custom-field schema; values have included
                # internal ticket URLs. Not worth preserving per-field -
                # drop the whole list.
                scrubbed[key] = []
            elif folded in _REDACT_TEXT_KEYS_FOLDED and isinstance(v, str) and v:
                scrubbed[key] = f"Sanitised {key}"
            else:
                scrubbed[key] = _scrub(v)
        return scrubbed
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _scrub_response(response: dict[str, Any]) -> dict[str, Any]:
    """VCR ``before_record_response`` hook: strip business content, PII, credentials, and host.

    Runs after ``decode_compressed_response`` (see ``_vcr_config`` below), so
    ``response["body"]["string"]`` is already-decompressed JSON bytes. A
    non-JSON or empty body (there are none in this suite, but future tests
    might add one) passes through unchanged rather than erroring.

    Response-side leak surface, in order:

    - ``Set-Cookie`` (and friends) and ``Content-Security-Policy`` (and its
      ``-Report-Only`` twin) are dropped outright - a server-issued session
      credential has no business in a fixture, vcrpy's ``filter_headers``
      never sees a response, and a browser policy naming every third-party
      origin the vendor's UI uses is neither exercised by the client nor
      scrubbable to a fixed point (see ``_DROPPED_HEADER_MARKERS``).
    - Remaining header values get the scrubbers applied (e.g. a ``Location``
      header echoing the domain back).
    - The raw body likewise, before JSON parsing, so a ``Next``/``Prev``
      pagination URL carrying the domain *or* the token is neutralised even
      though it lives in a key ``_scrub`` deliberately leaves alone.
    - Once parsed, ``_scrub`` replaces the free-text and identity fields
      inside ``Items``; entity Ids and the ``Next``/``Prev`` links are
      recorded as they came off the wire (see ``_REDACT_TEXT_KEYS``).
    """
    replacements = _sensitive_replacements()
    headers: dict[str, Any] = response.get("headers") or {}
    for key in [k for k in headers if _is_dropped_header(k)]:
        del headers[key]
    for key, values in headers.items():
        headers[key] = [_scrub_text(v, replacements) if isinstance(v, str) else v for v in values]

    body = response.get("body", {}).get("string")
    if not body:
        return response
    body = (
        _scrub_bytes(body, replacements)
        if isinstance(body, bytes)
        else _scrub_text(body, replacements)
    )
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        response["body"]["string"] = body
    else:
        scrubbed = _scrub(parsed)
        response["body"]["string"] = json.dumps(scrubbed).encode("utf-8")
    _resync_response_content_length(response)
    return response


def _vcr_config() -> dict[str, Any]:
    """The recording configuration, as a plain callable.

    Separate from the fixture below so a test can drive the *whole* pipeline -
    build a real ``vcr.VCR`` from this dict and inspect the YAML it writes -
    rather than only calling the hooks directly. Exercising the hooks in
    isolation cannot detect them being unwired from here, which is the
    regression this configuration is most exposed to.
    """
    return {
        "filter_query_parameters": [("access_token", _REDACTED)],
        # Request-side only: vcrpy applies these before ``before_record_request``
        # and never to a response, so a response-only header such as
        # ``Set-Cookie`` would be inert here - ``_scrub_response`` covers that
        # side instead. vcrpy matches these by exact name, so the request-side
        # cookie headers are enumerated rather than shape-matched;
        # ``_scrub_request`` is the backstop for any variant not named here.
        # ``proxy-authorization`` covers a corporate proxy on the recording
        # machine injecting its own credentials.
        "filter_headers": ["authorization", "proxy-authorization", "cookie", "cookie2"],
        # TP responses are gzip-compressed by default, which would otherwise
        # store each response body as an opaque base64 blob - undermining
        # both auditability (nobody can eyeball a cassette diff) and the
        # cassette guard's secret-scan (a compressed blob is indistinguishable
        # from a leaked token to a regex). Decoding at record time keeps
        # cassettes as plain, greppable JSON - and lets _scrub_response work
        # on real JSON rather than compressed bytes.
        "decode_compressed_response": True,
        "before_record_request": _scrub_request,
        "before_record_response": _scrub_response,
        "record_mode": "once" if os.environ.get("ALLOW_PROD_RECORDING") else "none",
    }


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    """Return the VCR recording configuration for the integration suite."""
    return _vcr_config()


@functools.cache
def _resolve_live_credentials() -> tuple[str, str]:
    """Resolve the (domain, token) pair used to construct the test client.

    Offline replay (the default - ``ALLOW_PROD_RECORDING`` unset) ignores
    any real credentials on this machine and always returns
    ``_PLACEHOLDER_DOMAIN``, the neutral host baked into the cassettes, so
    replay is deterministic everywhere regardless of whether a real
    ``~/.config/targetprocess/.env`` happens to exist - vcrpy's default
    request matcher includes the host, so mismatching it here would break
    every recorded interaction.

    Recording (``ALLOW_PROD_RECORDING=1``) reads the real token/domain from
    the environment or that file to hit the live API; the scrubbing hooks
    then neutralise both back onto their placeholders before the cassette is
    written. The base URL is parsed rather than string-trimmed so an
    ``http://`` scheme is stripped like ``https://`` is, while a non-default
    port survives into the domain the client is built from.

    Cached because it is consulted once per recorded interaction (via
    ``_sensitive_replacements``) as well as per test, and reads a file. Call
    ``cache_clear()`` if a test needs to vary the environment.
    """
    if not os.environ.get("ALLOW_PROD_RECORDING"):
        return _PLACEHOLDER_DOMAIN, _REDACTED

    env_path = Path.home() / ".config" / "targetprocess" / ".env"
    env: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("\"'")
    token = os.environ.get("TP_API_TOKEN") or env.get("TP_API_TOKEN") or _REDACTED
    base = (
        os.environ.get("TP_BASE_URL") or env.get("TP_BASE_URL") or f"https://{_PLACEHOLDER_DOMAIN}"
    )
    netloc = urlparse(base if "://" in base else f"https://{base}").netloc
    return (netloc or _PLACEHOLDER_DOMAIN).lower(), token


@pytest.fixture()
def live_credentials() -> tuple[str, str]:
    return _resolve_live_credentials()
