"""Guard test to ensure all recorded cassettes are free of leaked secrets.

Scans every VCR cassette (YAML) under tests/integration/cassettes/ for
patterns that would indicate an unredacted access token, authorization
header, or client-identifying value made it into a committed fixture. This
is a real content scan, not an honour-system marker: a cassette can only
pass by actually containing no matching pattern.

Why this matters:
- Cassettes are recorded against a real TargetProcess instance
  (tests/integration/, ALLOW_PROD_RECORDING=1) and then committed so the
  same tests can replay offline.
- The client sends its token as an `access_token` query parameter (see
  targetprocess.transport._QueryTokenAuth), so that's the primary leak
  surface; the authorization-header pattern and the loose base64 pattern
  are belt-and-braces for the Basic-auth alternative and any other
  token-shaped secret.
- tests/integration/conftest.py's `filter_query_parameters` config already
  redacts the token at record time - this test is the independent check
  that catches it if that ever regresses.
- The real customer's TP domain identifies the client this repo was
  recorded against and must never appear in a public release fixture;
  tests/integration/conftest.py's `_scrub_request`/`_scrub_response` hooks
  already neutralise it onto the placeholder domain at record time - this is
  the independent check that catches it if that ever regresses.

Cookie headers are checked separately, by `cookie_header_offenders` below:
they are a structural question about a cassette's header mappings rather than
a text pattern, and the distinction is load-bearing (see that docstring).

This scan runs over committed cassettes, so it can only catch a leak once
someone has recorded and staged one. tests/test_cassette_sanitiser.py is the
upstream half of the pair: it drives the recording pipeline directly, and
cross-checks its output against both controls here, so each is exercised
against output the other produced.
"""

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

CASSETTE_DIR = Path(__file__).parent / "integration" / "cassettes"

# The fields the record hooks replace with a ``Sanitised <Field>`` placeholder,
# folded, and the prefix that placeholder starts with. Declared here rather
# than imported from the recording conftest on purpose: this scan is the
# *independent* half of the pair, and a guard that read its expectations from
# the thing it guards would pass by construction the moment that thing shrank.
_REDACTED_FIELD_NAMES = {
    "name",
    "description",
    "firstname",
    "lastname",
    "fullname",
    "login",
    "tags",
    "uniquefilename",
}
_PLACEHOLDER_PREFIX = "Sanitised "

# Substring, not an enumeration. Cookie headers carry a live session
# credential in either direction, and the family is open-ended -
# `Cookie`/`Cookie2` (RFC 2965) request-side, `Set-Cookie`/`Set-Cookie2`
# response-side, plus whatever a proxy invents. Naming them individually means
# a miss is silent and permanent; matching the shape means a new variant is
# caught by default. A guard should fail towards noise, never towards silence.
_COOKIE_HEADER_MARKER = "cookie"

# Same shape-match, same reason: the record hooks drop the whole
# Content-Security-Policy family rather than scrub it, so the substring also
# covers ``Content-Security-Policy-Report-Only`` and any casing.
_CSP_HEADER_MARKER = "content-security-policy"


def _is_cookie_header(name: str) -> bool:
    return _COOKIE_HEADER_MARKER in name.lower()


def _is_csp_header(name: str) -> bool:
    return _CSP_HEADER_MARKER in name.lower()


# Split so this scanner's own source doesn't contain the contiguous
# client-identifying string it exists to catch (a repo-wide grep for it
# would otherwise flag this very definition as a hit).
_CLIENT_DOMAIN_FRAGMENT = "bulk" + "sms"

SECRET_PATTERNS = [
    re.compile(r"""(?i)access_token=(?!REDACTED(?:[&'"\s]|$))[^&'"\s]+"""),
    # `[ \t]+` (not `\s+`) after the colon - `\s` would cross the newline into
    # the list-header form below and false-positive on its "- " marker as if
    # it were a non-redacted value.
    re.compile(r"(?im)^\s*authorization:[ \t]+(?!REDACTED(?:\s|$))\S+"),
    re.compile(r"(?im)^\s*authorization:\s*$\n\s*-\s+(?!REDACTED(?:\s|$))\S+"),
    re.compile(r"[A-Za-z0-9+/]{30,}={1,2}"),  # loose base64 - TP tokens are base64
    re.compile(f"(?i){_CLIENT_DOMAIN_FRAGMENT}"),  # real client identifier - must never appear
    # Any TargetProcess host other than the placeholder: a tenant host under a
    # different label, or one of the vendor's own hosts that a response's
    # Content-Security-Policy names - infrastructure and CDN
    # (``*.tpondemand.net``, ``*.cdntpondemand.com``) and corporate
    # (``*.targetprocess.com``, ``tauboard.com``). The record-time scrubber
    # rewrites every one of these to the placeholder; this is the independent
    # check that it did. Matched as a whole host token (the lookbehind stops a
    # match starting mid-label), with exactly ``example.tpondemand.com``
    # exempted by the lookahead - a tenant label that merely *ends* in
    # "example" is still a hit.
    re.compile(
        r"(?i)(?<![A-Za-z0-9*.-])(?!example\.tpondemand\.com(?![A-Za-z0-9-]))"
        r"(?:[A-Za-z0-9*-]+\.)*"
        r"(?:(?:cdn)?tpondemand\.(?:com|net)|targetprocess\.com|tauboard\.com)"
    ),
]


def _header_offenders(cassette_text: str, is_offender: Callable[[str], bool]) -> list[str]:
    """Names of the headers ``is_offender`` matches, present in a serialised cassette.

    Structural rather than a text pattern, because "does this cassette carry a
    Set-Cookie *header*" is a question about its header mappings, not about its
    characters. A raw `^\\s*set-cookie:` scan also fires on that text inside a
    folded body block - reachable, not theoretical - and tightening it to the
    header-key form trades that false positive for a false negative under a
    different YAML serialisation. On a security guard the false negative is by
    far the worse error, so neither regex is the right instrument; parsing
    removes both failure modes at once.
    """
    document: Any = yaml.safe_load(cassette_text) or {}
    offenders = []
    for interaction in document.get("interactions") or []:
        for side in ("request", "response"):
            headers = (interaction.get(side) or {}).get("headers") or {}
            offenders += [f"{side}.{k}" for k in headers if is_offender(k)]
    return offenders


def cookie_header_offenders(cassette_text: str) -> list[str]:
    """Names of any cookie-carrying headers present in a serialised cassette."""
    return _header_offenders(cassette_text, _is_cookie_header)


def csp_header_offenders(cassette_text: str) -> list[str]:
    """Names of any Content-Security-Policy headers present in a serialised cassette.

    The record hooks drop the header outright (``-Report-Only`` included):
    a browser policy names every third-party origin the vendor's web UI
    talks to, none of which a client fixture exercises, and no host
    scrubber converges on such a list. Structural for the same reason the
    cookie check is - the question is about the header mapping, not the
    characters.
    """
    return _header_offenders(cassette_text, _is_csp_header)


def _response_bodies(cassette_text: str) -> Iterator[Any]:
    """Yield each interaction's parsed response body, skipping the non-JSON ones.

    Response bodies only. A *request* body is recorded exactly as sent and is
    deliberately not field-scrubbed, because a write-path test may only ever
    send text it invented (see ``docs/testing.md``); scanning it here would
    flag the synthetic names those tests are required to use.
    """
    document: Any = yaml.safe_load(cassette_text) or {}
    for interaction in document.get("interactions") or []:
        body = ((interaction.get("response") or {}).get("body") or {}).get("string")
        if not body:
            continue
        try:
            yield json.loads(body)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue


def identity_field_offenders(cassette_text: str) -> list[str]:
    """Free-text/identity fields in a cassette's response bodies that are not placeholders.

    The independent counterpart to the record-time redaction in
    ``tests/integration/conftest.py``, and the only check that can catch the
    failure mode the sanitiser suite structurally cannot. That suite's
    fixed-point test asserts the hooks change nothing when re-run over a
    committed cassette - but a field whose key the hooks do not recognise *is*
    a fixed point, so a leaked value satisfies it perfectly while sitting in
    the file. Asking instead "does every field that should be a placeholder
    hold one" is blind to which keys the hooks happen to know about.

    Matched case-insensitively for the reason the record hooks are: the JSON
    entity API answers in PascalCase and the file endpoint in camelCase.
    An empty value is not an offender - the hooks replace a field's text only
    when there is text to replace.
    """
    offenders = []
    for body in _response_bodies(cassette_text):
        offenders += [f"{key}={value!r}" for key, value in _text_fields(body)]
    return offenders


def _text_fields(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Walk a parsed body, yielding every redaction-set field that is not a placeholder."""
    if isinstance(value, dict):
        for key, nested in value.items():
            here = f"{path}.{key}" if path else key
            if (
                key.lower() in _REDACTED_FIELD_NAMES
                and isinstance(nested, str)
                and nested
                and not nested.startswith(_PLACEHOLDER_PREFIX)
            ):
                yield here, nested
            else:
                yield from _text_fields(nested, here)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _text_fields(item, f"{path}[{index}]")


def test_cassettes_carry_no_unredacted_identity_fields() -> None:
    cassettes = list(CASSETTE_DIR.rglob("*.yaml"))
    assert cassettes, "no cassettes recorded — integration layer missing"
    offenders = {
        c.name: found for c in cassettes if (found := identity_field_offenders(c.read_text()))
    }
    assert not offenders, f"unredacted identity fields in cassettes: {offenders}"


def test_identity_field_offenders_flags_a_leak_whatever_its_casing() -> None:
    """The positive control: a clean sweep of the real cassettes proves nothing alone.

    Both casings, because the leak this guard exists for arrived in camelCase
    from a file endpoint while the redaction set was written in PascalCase.
    """
    leaky = _body_cassette(
        {
            "Items": [{"Id": 1, "Name": "A real story title"}],
            "items": [{"owner": {"login": "areallogin", "fullName": "A Real Person"}}],
        }
    )

    offenders = identity_field_offenders(leaky)

    assert sorted(offenders) == [
        "Items[0].Name='A real story title'",
        "items[0].owner.fullName='A Real Person'",
        "items[0].owner.login='areallogin'",
    ]


def test_identity_field_offenders_accepts_placeholders_and_empty_values() -> None:
    """Scrubbed and absent both pass - the hooks only replace text that is there."""
    clean = _body_cassette(
        {
            "Items": [
                {"Id": 1, "Name": "Sanitised Name", "Description": "", "Tags": None},
                {"Id": 2, "uniqueFileName": "Sanitised uniqueFileName"},
            ]
        }
    )

    assert identity_field_offenders(clean) == []


def test_identity_field_offenders_ignores_a_request_body() -> None:
    """A write-path request body is recorded as sent and carries invented text."""
    document = yaml.safe_load(_body_cassette({"Items": []}))
    document["interactions"][0]["request"]["body"] = json.dumps(
        {"Name": "Invented story name, recorded as sent"}
    )

    assert identity_field_offenders(yaml.safe_dump(document)) == []


def _body_cassette(body: dict[str, Any]) -> str:
    """Serialise a one-interaction cassette carrying the given JSON response body."""
    return yaml.safe_dump(
        {
            "interactions": [
                {
                    "request": {"headers": {}, "body": None},
                    "response": {"headers": {}, "body": {"string": json.dumps(body)}},
                }
            ]
        }
    )


def test_cassettes_contain_no_secrets() -> None:
    cassettes = list(CASSETTE_DIR.rglob("*.yaml"))
    assert cassettes, "no cassettes recorded — integration layer missing"
    offenders = [
        (c.name, p.pattern) for c in cassettes for p in SECRET_PATTERNS if p.search(c.read_text())
    ]
    assert not offenders, f"secrets leaked into cassettes: {offenders}"


def _cassette_yaml(request_headers: dict[str, Any], response_headers: dict[str, Any]) -> str:
    document = {
        "interactions": [
            {
                "request": {
                    "uri": "https://example.tpondemand.com/x",
                    "headers": request_headers,
                },
                "response": {"headers": response_headers, "body": {"string": "{}"}},
            }
        ],
        "version": 1,
    }
    dumped: str = yaml.dump(document)
    return dumped


def test_cookie_header_offenders_detects_both_directions() -> None:
    """A guard that has never produced a positive is not known to work."""
    offenders = cookie_header_offenders(
        _cassette_yaml(
            {"Cookie": ["sid=abc"], "Cookie2": ['$Version="1"']},
            {"Set-Cookie": ["sid=def"], "SET-COOKIE2": ["x=1"]},
        )
    )

    assert sorted(offenders) == [
        "request.Cookie",
        "request.Cookie2",
        "response.SET-COOKIE2",
        "response.Set-Cookie",
    ]


def test_cookie_header_offenders_ignores_matching_text_in_a_body() -> None:
    """The reason this is structural: `set-cookie:` is legal body content."""
    document = yaml.safe_load(_cassette_yaml({}, {"content-type": ["application/json"]}))
    document["interactions"][0]["response"]["body"]["string"] = (
        "x" * 50 + "\nset-cookie: sid=fromBody\n" + "y" * 50
    )

    assert cookie_header_offenders(yaml.dump(document)) == []


def test_cassettes_carry_no_cookie_headers() -> None:
    cassettes = list(CASSETTE_DIR.rglob("*.yaml"))
    assert cassettes, "no cassettes recorded — integration layer missing"
    offenders = [
        (c.name, header) for c in cassettes for header in cookie_header_offenders(c.read_text())
    ]
    assert not offenders, f"cookie headers leaked into cassettes: {offenders}"


def test_csp_header_offenders_detects_the_header_and_its_report_only_twin() -> None:
    """A guard that has never produced a positive is not known to work."""
    offenders = csp_header_offenders(
        _cassette_yaml(
            {"Accept": ["application/json"]},
            {
                "Content-Security-Policy": ["default-src 'self' https://analytics.example"],
                "content-security-policy-report-only": ["default-src 'none'"],
                "Content-Type": ["application/json"],
            },
        )
    )

    assert sorted(offenders) == [
        "response.Content-Security-Policy",
        "response.content-security-policy-report-only",
    ]


def test_cassettes_carry_no_csp_headers() -> None:
    cassettes = list(CASSETTE_DIR.rglob("*.yaml"))
    assert cassettes, "no cassettes recorded — integration layer missing"
    offenders = [
        (c.name, header) for c in cassettes for header in csp_header_offenders(c.read_text())
    ]
    assert not offenders, f"Content-Security-Policy headers left in cassettes: {offenders}"


@pytest.mark.parametrize(
    "host",
    [
        "notexample.tpondemand.com",  # a tenant label that merely ends in "example"
        "acme.eu.tpondemand.com",
        "solutions.tpondemand.net",
        "*.cdntpondemand.com",
        "www.targetprocess.com",
        "tauboard.com",
        "EXAMPLE2.TPONDEMAND.COM",
    ],
)
def test_host_pattern_flags_every_tp_host_that_is_not_the_placeholder(host: str) -> None:
    line = f"        content-security-policy: default-src https://{host}/x https://cdnjs.cloudflare.com"
    assert any(pattern.search(line) for pattern in SECRET_PATTERNS), host


@pytest.mark.parametrize(
    "line",
    [
        "    uri: https://example.tpondemand.com/api/v1/UserStories?format=json",
        "        host: example.tpondemand.com",
        "        - https://Example.TPOnDemand.com https://cdnjs.cloudflare.com",
    ],
)
def test_host_pattern_exempts_exactly_the_placeholder(line: str) -> None:
    assert not any(pattern.search(line) for pattern in SECRET_PATTERNS), line
