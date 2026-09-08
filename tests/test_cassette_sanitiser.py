"""Unit tests for the cassette-recording sanitiser hooks.

``tests/test_cassette_guard.py`` scans committed cassettes and so can only
catch a leak *after* someone has recorded and staged one. These tests
exercise the recording pipeline in ``tests/integration/conftest.py``
directly, against a simulated recording session, so a gap fails immediately
rather than waiting for the next recording run.

Two layers, because the hooks being *correct* and the hooks being *reachable*
are separate failure modes:

- The hook-level tests call ``_scrub_request``/``_scrub_response`` directly.
  They pin the behaviour of each carrier.
- ``test_recording_pipeline_writes_a_clean_cassette`` drives a real
  ``vcr.VCR`` built from ``_vcr_config()`` and greps the YAML vcrpy actually
  writes to disk. Hook-level tests alone cannot detect the hooks being
  unwired from that config - the suite would stay green while every
  subsequent recording leaked - so this one is the load-bearing gate.
- ``test_record_hooks_are_stable_over_every_committed_cassette`` runs both
  hooks over the real committed cassettes in offline mode: the request and
  the response body must come back as recorded, and a second pass must
  change nothing. vcrpy re-runs the hooks on ``Cassette.load()``, so a hook
  that drifts on already-sanitised content corrupts every cassette in
  memory on every replay.

The domain and token used here are fabricated - they only need to be values
the hooks have never seen before.
"""

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import vcr  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]
from vcr.request import Request  # type: ignore[import-untyped]
from vcr.serialize import deserialize  # type: ignore[import-untyped]
from vcr.serializers import yamlserializer  # type: ignore[import-untyped]

from tests.integration import conftest as sanitiser
from tests.test_cassette_guard import (
    CASSETTE_DIR,
    SECRET_PATTERNS,
    cookie_header_offenders,
    csp_header_offenders,
)

REAL_DOMAIN = "acme-customer.tpondemand.com"
# A sibling tenant on the same TP estate: never configured and never seen on
# the wire, so the exact-match registry cannot know about it. Only the
# shape-matched catch-all reaches this one.
SIBLING_DOMAIN = "acme-customer.eu.tpondemand.com"
# Long enough, and padded, to trip the guard's loose-base64 pattern if it ever
# reaches a cassette - so the cross-check below is a real check.
REAL_TOKEN = "cmVhbHRva2VudmFsdWVsb25nZW5vdWdodG90cmlwZ3VhcmQ="
PLACEHOLDER = sanitiser._PLACEHOLDER_DOMAIN
REDACTED = sanitiser._REDACTED


@pytest.fixture()
def recording(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Simulate a live recording session with real credentials configured."""
    monkeypatch.setenv("ALLOW_PROD_RECORDING", "1")
    monkeypatch.setenv("TP_BASE_URL", f"https://{REAL_DOMAIN}")
    monkeypatch.setenv("TP_API_TOKEN", REAL_TOKEN)
    sanitiser._resolve_live_credentials.cache_clear()
    sanitiser._last_request_host.clear()
    yield
    sanitiser._resolve_live_credentials.cache_clear()
    sanitiser._last_request_host.clear()


@pytest.fixture()
def offline(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Simulate an ordinary offline replay run, with the same teardown guarantees."""
    monkeypatch.delenv("ALLOW_PROD_RECORDING", raising=False)
    sanitiser._resolve_live_credentials.cache_clear()
    sanitiser._last_request_host.clear()
    yield
    sanitiser._resolve_live_credentials.cache_clear()
    sanitiser._last_request_host.clear()


def _request(uri: str, body: bytes | None = None) -> Request:
    host = uri.split("//", 1)[1].split("/", 1)[0]
    return Request("GET", uri, body, {"host": host, "user-agent": "python-httpx/0.28.1"})


@pytest.mark.usefixtures("recording")
def test_request_host_header_is_rewritten() -> None:
    """The regression this module exists for: the URI alone is not enough."""
    scrubbed = sanitiser._scrub_request(_request(f"https://{REAL_DOMAIN}/api/v1/Comments"))

    assert scrubbed.headers["host"] == PLACEHOLDER
    assert scrubbed.uri == f"https://{PLACEHOLDER}/api/v1/Comments"
    assert REAL_DOMAIN not in str(dict(scrubbed.headers))


@pytest.mark.usefixtures("recording")
def test_request_body_and_token_are_scrubbed() -> None:
    body = f'{{"Url": "https://{REAL_DOMAIN}/entity/1?access_token={REAL_TOKEN}"}}'.encode()
    scrubbed = sanitiser._scrub_request(
        _request(f"https://{REAL_DOMAIN}/api/v1/UserStories", body=body)
    )

    assert (
        scrubbed.body
        == f'{{"Url": "https://{PLACEHOLDER}/entity/1?access_token=REDACTED"}}'.encode()
    )


@pytest.mark.usefixtures("recording")
def test_request_content_length_follows_the_scrubbed_body() -> None:
    body = f'{{"Url": "https://{REAL_DOMAIN}/x"}}'.encode()
    request = Request(
        "POST",
        f"https://{REAL_DOMAIN}/api/v1/UserStories",
        body,
        {"host": REAL_DOMAIN, "content-length": str(len(body))},
    )

    scrubbed = sanitiser._scrub_request(request)

    assert scrubbed.headers["content-length"] == str(len(scrubbed.body))


@pytest.mark.usefixtures("recording")
def test_request_scrubs_host_echoed_in_other_headers() -> None:
    request = _request(f"https://{REAL_DOMAIN}/api/v1/Comments")
    request.headers["referer"] = f"https://{REAL_DOMAIN}/board"

    scrubbed = sanitiser._scrub_request(request)

    assert scrubbed.headers["referer"] == f"https://{PLACEHOLDER}/board"


@pytest.mark.usefixtures("recording")
def test_request_cookie_headers_are_dropped_by_shape() -> None:
    """A session credential is not made safe by scrubbing a domain inside it.

    `filter_headers` removes the names it lists; this covers the variants it
    does not, which is why the match is on shape rather than an enumeration.
    """
    request = _request(f"https://{REAL_DOMAIN}/api/v1/Comments")
    request.headers["Cookie2"] = '$Version="1"'
    request.headers["X-Vendor-Cookie"] = "sid=abc"

    scrubbed = sanitiser._scrub_request(request)

    assert [k for k in scrubbed.headers if "cookie" in k.lower()] == []
    assert scrubbed.headers["host"] == PLACEHOLDER  # non-cookie headers survive


@pytest.mark.usefixtures("recording")
def test_request_with_unscrubbable_body_type_fails_loudly() -> None:
    """A body the scrubbers cannot read must abort, not serialise unexamined."""
    request = Request("POST", f"https://{REAL_DOMAIN}/api/v1/Attachments", object(), {})

    with pytest.raises(TypeError, match="Cannot scrub request body"):
        sanitiser._scrub_request(request)


@pytest.mark.usefixtures("offline")
def test_request_is_untouched_on_offline_replay() -> None:
    scrubbed = sanitiser._scrub_request(_request(f"https://{PLACEHOLDER}/api/v1/Comments"))

    assert scrubbed.uri == f"https://{PLACEHOLDER}/api/v1/Comments"
    assert scrubbed.headers["host"] == PLACEHOLDER


@pytest.mark.usefixtures("recording")
def test_response_set_cookie_is_dropped() -> None:
    response = {
        "headers": {"Set-Cookie": ["sid=abc123; Path=/"], "Content-Type": ["application/json"]},
        "body": {"string": b"{}"},
    }

    scrubbed = sanitiser._scrub_response(response)

    assert "Set-Cookie" not in scrubbed["headers"]
    assert scrubbed["headers"]["Content-Type"] == ["application/json"]


@pytest.mark.usefixtures("recording")
def test_response_headers_and_body_are_scrubbed() -> None:
    sanitiser._scrub_request(_request(f"https://{REAL_DOMAIN}/api/v1/Comments"))
    body = (
        f'{{"Next": "https://{REAL_DOMAIN}/api/v1/Comments/?access_token={REAL_TOKEN}&skip=2",'
        f' "Items": [{{"Id": 1, "Name": "Real story title"}}]}}'
    ).encode()
    response = {
        "headers": {"Location": [f"https://{REAL_DOMAIN}/api/v1/Comments/2"]},
        "body": {"string": body},
    }

    scrubbed = sanitiser._scrub_response(response)

    recorded = scrubbed["body"]["string"].decode()
    assert REAL_DOMAIN not in recorded
    assert REAL_TOKEN not in recorded
    assert PLACEHOLDER in recorded
    assert "Real story title" not in recorded  # free text still redacted
    assert scrubbed["headers"]["Location"] == [f"https://{PLACEHOLDER}/api/v1/Comments/2"]


@pytest.mark.usefixtures("recording")
def test_response_redacts_identity_fields_whatever_their_casing() -> None:
    """The file endpoint answers in camelCase, and its body carries the uploader.

    ``/UploadFile.ashx`` sits outside ``/api/v1`` and does not follow the
    JSON entity API's PascalCase: it returns ``firstName``/``lastName``/
    ``login``/``fullName`` for the uploading user. An exact-case match
    recognises none of them, so the redaction set is matched case-folded -
    this is the test that holds it that way.
    """
    sanitiser._scrub_request(_request(f"https://{REAL_DOMAIN}/UploadFile.ashx"))
    body = json.dumps(
        {
            "items": [
                {
                    "resourceType": "Attachment",
                    "id": 7,
                    "name": "invented-fixture.txt",
                    "size": 63,
                    "customFields": [{"name": "Ticket", "value": "internal-only"}],
                    "owner": {
                        "resourceType": "GeneralUser",
                        "id": 1,
                        "firstName": "Alex",
                        "lastName": "Example",
                        "login": "alex",
                        "fullName": "Alex Example",
                    },
                }
            ]
        }
    ).encode()

    scrubbed = sanitiser._scrub_response({"headers": {}, "body": {"string": body}})

    recorded = json.loads(scrubbed["body"]["string"])
    owner = recorded["items"][0]["owner"]
    assert owner["firstName"] == "Sanitised firstName"
    assert owner["lastName"] == "Sanitised lastName"
    assert owner["login"] == "Sanitised login"
    assert owner["fullName"] == "Sanitised fullName"
    assert recorded["items"][0]["name"] == "Sanitised name"
    # Dropped wholesale by the same folded match, not merely field-scrubbed.
    assert recorded["items"][0]["customFields"] == []
    # Structural values still come off the wire untouched.
    assert recorded["items"][0]["id"] == 7
    assert recorded["items"][0]["size"] == 63


@pytest.mark.usefixtures("recording")
def test_entity_ids_are_recorded_as_received() -> None:
    """Ids are structural, and a rewritten one would defeat the filter assertions.

    ``test_priorities_scoped_to_an_entity_type`` reads ``EntityType.Id`` as
    the only surviving evidence that a ``where=`` filter narrowed the result
    (every ``Name`` is a placeholder), so an Id must come off the wire
    intact - in ``Items``, in a nested reference, in the ``where=`` clause
    the server echoes into ``Next``, and in the follow-up request that
    ``TimesResource.find_for_day`` builds from it.
    """
    entity_id, assignable_id = 68395, 71234
    where = f"where=%28Assignable.Id+eq+{assignable_id}%29"
    body = json.dumps(
        {
            "Items": [{"Id": entity_id, "Assignable": {"Id": assignable_id}, "Name": "Real story"}],
            "Next": f"https://{REAL_DOMAIN}/api/v1/Times/?{where}&skip=10",
        }
    ).encode()

    response = sanitiser._scrub_response({"headers": {}, "body": {"string": body}})
    request = sanitiser._scrub_request(_request(f"https://{REAL_DOMAIN}/api/v1/Times/?{where}"))

    recorded = json.loads(response["body"]["string"].decode())
    assert recorded["Items"][0]["Id"] == entity_id
    assert recorded["Items"][0]["Assignable"]["Id"] == assignable_id
    assert recorded["Items"][0]["Name"] == "Sanitised Name"  # free text still redacted
    assert recorded["Next"] == f"https://{PLACEHOLDER}/api/v1/Times/?{where}&skip=10"
    assert request.uri == f"https://{PLACEHOLDER}/api/v1/Times/?{where}"


@pytest.mark.usefixtures("recording")
def test_response_content_length_follows_the_scrubbed_body() -> None:
    """Both exit paths rewrite the body, so neither may leave the header behind."""
    json_response = {
        "headers": {"Content-Length": ["9999"]},
        "body": {"string": f'{{"Next": "https://{REAL_DOMAIN}/x", "Items": []}}'.encode()},
    }
    text_response = {
        "headers": {"Content-Length": ["9999"]},
        "body": {"string": f"plain {REAL_DOMAIN}".encode()},
    }

    for response in (json_response, text_response):
        scrubbed = sanitiser._scrub_response(response)
        assert scrubbed["headers"]["Content-Length"] == [str(len(scrubbed["body"]["string"]))]


@pytest.mark.usefixtures("recording")
def test_response_non_json_body_survives_scrubbing() -> None:
    response = {"headers": {}, "body": {"string": f"plain text {REAL_DOMAIN}".encode()}}

    scrubbed = sanitiser._scrub_response(response)

    assert scrubbed["body"]["string"] == f"plain text {PLACEHOLDER}".encode()


@pytest.mark.usefixtures("recording")
def test_response_scrubs_host_the_registry_cannot_know_about() -> None:
    """Case variance and sibling tenants are the server's choice, not ours.

    Neither value is ever configured or seen on the wire, so the exact-match
    registry is blind to both; only the shape-matched catch-all reaches them.
    """
    response = {
        "headers": {"Location": [f"https://{SIBLING_DOMAIN}/api/v1/Target"]},
        "body": {"string": f'{{"Note": "see https://{REAL_DOMAIN.upper()}/x"}}'.encode()},
    }

    scrubbed = sanitiser._scrub_response(response)

    assert scrubbed["headers"]["Location"] == [f"https://{PLACEHOLDER}/api/v1/Target"]
    assert REAL_DOMAIN.upper() not in scrubbed["body"]["string"].decode()
    assert PLACEHOLDER in scrubbed["body"]["string"].decode()


def test_response_drops_content_security_policy_outright() -> None:
    """A browser policy is removed at record time, not rewritten.

    It names every third-party origin the vendor's web UI talks to -
    analytics, identity providers, support widgets - none of which a client
    fixture exercises, and a host list no scrubber converges on. The
    ``-Report-Only`` twin goes with it, in any casing; every other header
    stays, with the host scrubber still covering what it carries.
    """
    csp = (
        "default-src 'self' https://solutions.tpondemand.net https://*.cdntpondemand.com "
        "https://www.targetprocess.com https://tauboard.com https://analytics.example"
    )
    response = {
        "headers": {
            "Content-Security-Policy": [csp],
            "content-security-policy-report-only": ["default-src 'none'"],
            "Location": ["https://awsinfra.tpondemand.net/x"],
            "Content-Type": ["application/json"],
        },
        "body": {"string": b'{"Note": "https://Solutions.TPOnDemand.NET/x"}'},
    }

    scrubbed = sanitiser._scrub_response(response)

    assert set(scrubbed["headers"]) == {"Location", "Content-Type"}
    assert scrubbed["headers"]["Location"] == [f"https://{PLACEHOLDER}/x"]
    assert scrubbed["body"]["string"] == f'{{"Note": "https://{PLACEHOLDER}/x"}}'.encode()
    # The guard's independent scan would have flagged the policy's hosts;
    # after the hook there is no header left for it to look at.
    assert any(p.search(csp) for p in SECRET_PATTERNS)
    remaining = [v for values in scrubbed["headers"].values() for v in values]
    assert not any(p.search(v) for v in remaining for p in SECRET_PATTERNS)


def test_vcr_config_wires_both_scrubbing_hooks() -> None:
    """Fast canary for the failure mode the end-to-end test below actually gates."""
    config = sanitiser._vcr_config()

    assert config["before_record_request"] is sanitiser._scrub_request
    assert config["before_record_response"] is sanitiser._scrub_response


def _leaky_interactions() -> list[tuple[Request, dict[str, object]]]:
    """One interaction per carrier a real value could ride into a cassette."""
    read_request = Request(
        "GET",
        f"https://{REAL_DOMAIN}/api/v1/UserStory?take=1&access_token={REAL_TOKEN}",
        b"",
        {
            "host": REAL_DOMAIN,
            "origin": f"https://{REAL_DOMAIN}",
            "referer": f"https://{REAL_DOMAIN}/board?token={REAL_TOKEN}",
            "authorization": f"Basic {REAL_TOKEN}",
            "cookie": f"sid=abc; tpdomain={REAL_DOMAIN}",
            "cookie2": '$Version="1"',
            "x-tp-instance": REAL_DOMAIN,
        },
    )
    read_response = {
        "status": {"code": 200, "message": "OK"},
        "headers": {
            "content-type": ["application/json"],
            # Deliberately the pre-scrub length: the recorded value must follow
            # the sanitised body, not the body the server sent.
            "content-length": ["4096"],
            "set-cookie": [f"tpsession=liveSecret; Domain={REAL_DOMAIN}; Path=/"],
            "content-security-policy": [f"connect-src wss://{REAL_DOMAIN}"],
            "link": [f'<https://{REAL_DOMAIN}/api/v1/UserStory?skip=1>; rel="next"'],
        },
        "body": {
            "string": (
                f'{{"Next": "https://{REAL_DOMAIN}/api/v1/UserStory/'
                f'?access_token={REAL_TOKEN}&skip=1",'
                f' "Items": [{{"Id": 1, "Name": "Real Story"}}]}}'
            ).encode()
        },
    }

    # Write-path POST: the carrier the recorded write cassettes depend on.
    write_body = f'{{"Name":"x","Url":"https://{REAL_DOMAIN}/entity/1"}}'.encode()
    write_request = Request(
        "POST",
        f"https://{REAL_DOMAIN}/api/v1/UserStories?access_token={REAL_TOKEN}",
        write_body,
        {
            "host": REAL_DOMAIN,
            "content-type": ["application/json"],
            "content-length": str(len(write_body)),
        },
    )
    write_response = {
        "status": {"code": 201, "message": "Created"},
        "headers": {
            "content-type": ["application/json"],
            "location": [f"https://{SIBLING_DOMAIN}/api/v1/UserStories/99"],
        },
        "body": {"string": b'{"Id": 99}'},
    }

    return [(read_request, read_response), (write_request, write_response)]


@pytest.mark.usefixtures("recording")
def test_recording_pipeline_writes_a_clean_cassette(tmp_path: Path) -> None:
    """Drive the real vcrpy pipeline and grep the YAML it writes.

    This is the test that would catch the hooks being unwired from
    ``_vcr_config()``, a carrier being missed, or vcrpy changing where a
    filter applies - none of which the hook-level tests above can see.
    """
    cassette_path = tmp_path / "pipeline.yaml"

    with vcr.VCR(**sanitiser._vcr_config()).use_cassette(str(cassette_path)) as cassette:
        for request, response in _leaky_interactions():
            cassette.append(request, response)

    recorded = cassette_path.read_text()

    assert REAL_DOMAIN not in recorded.lower()
    assert SIBLING_DOMAIN not in recorded.lower()
    assert REAL_TOKEN not in recorded
    assert "liveSecret" not in recorded
    # Prove the scrubbers ran, rather than the values merely never arriving.
    assert PLACEHOLDER in recorded
    assert REDACTED in recorded
    # Cross-check against the committed-cassette guard, so the two controls
    # test each other rather than agreeing by coincidence.
    assert [p.pattern for p in SECRET_PATTERNS if p.search(recorded)] == []
    assert cookie_header_offenders(recorded) == []
    assert csp_header_offenders(recorded) == []

    for interaction in yaml.safe_load(recorded)["interactions"]:
        response = interaction["response"]
        declared = {k.lower(): v for k, v in response["headers"].items()}.get("content-length")
        if declared is not None:
            body = response["body"]["string"] or ""
            actual = len(body.encode("utf-8") if isinstance(body, str) else body)
            assert declared == [str(actual)]


def _as_recorded(request: Request) -> tuple[str, str, bytes | str | None, dict[str, str]]:
    """The four request fields vcrpy serialises, as a comparable value."""
    return request.method, request.uri, request.body, dict(request.headers)


def _as_loaded(response: dict[str, Any]) -> dict[str, Any]:
    """The most a committed response may change on one pass of the hooks at load time.

    Exactly two normalisations are permitted, both confined to headers: the
    shape-matched TP-host pass over every header value, and ``Content-Length``
    recomputed from the body. Both are fixed points over a committed cassette
    - the hosts are already placeholders and the length already follows the
    body - and the headers the hooks drop (cookies, Content-Security-Policy)
    are never on disk to begin with. Status and body stay exactly as recorded.
    """
    loaded = copy.deepcopy(response)
    loaded["headers"] = {
        key: [sanitiser._neutralise_tp_hosts(v) if isinstance(v, str) else v for v in values]
        for key, values in response["headers"].items()
    }
    for key in loaded["headers"]:
        if key.lower() == "content-length":
            loaded["headers"][key] = [str(sanitiser._body_length(response["body"]["string"]))]
    return loaded


@pytest.mark.usefixtures("offline")
def test_record_hooks_are_stable_over_every_committed_cassette() -> None:
    """vcrpy re-runs both hooks on ``Cassette.load()``, so on replay they must not drift.

    Checked over the real committed cassettes rather than a synthetic body, so
    it covers exactly the content the replay path loads. The request, and the
    response status and body, must come back byte-for-byte as recorded: a
    hook that rewrote any of them would corrupt every cassette in memory on
    every offline run, and a response Id re-used to build a later request
    would no longer match the interaction recorded for it. Response headers
    may see only the two normalisations ``_as_loaded`` names, and the whole
    interaction must then be a fixed point of a second pass.
    """
    cassettes = sorted(CASSETTE_DIR.rglob("*.yaml"))
    assert cassettes, "no cassettes recorded — integration layer missing"

    for cassette in cassettes:
        requests, responses = deserialize(cassette.read_text(), yamlserializer)
        assert requests, cassette.name
        for request, response in zip(requests, responses, strict=True):
            recorded_request, loaded_response = _as_recorded(request), _as_loaded(response)

            first = (
                _as_recorded(sanitiser._scrub_request(request)),
                copy.deepcopy(sanitiser._scrub_response(response)),
            )
            second = (
                _as_recorded(sanitiser._scrub_request(request)),
                sanitiser._scrub_response(response),
            )

            assert first == (recorded_request, loaded_response), cassette.name
            assert second == first, cassette.name
