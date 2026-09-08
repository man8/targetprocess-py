"""Tests for the observability module: logging, scrubbing, and request-ID propagation."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

import httpx
import pytest

from targetprocess import (
    REQUEST_ID_HEADER,
    ScrubbingFilter,
    StructuredJsonFormatter,
    current_request_id,
    get_logger,
    new_request_id,
    request_id_context,
)
from targetprocess._observability import (
    logger as tp_logger,
)
from targetprocess._observability import (
    scrub_headers,
    scrub_message,
    scrub_url,
)
from targetprocess.exceptions import NetworkError
from targetprocess.request_handler import RequestHandler
from targetprocess.transport import HTTPTransport

# ---------------------------------------------------------------------------
# scrub_url
# ---------------------------------------------------------------------------


def test_scrub_url_redacts_access_token() -> None:
    url = "https://example.tpondemand.com/api/v1/UserStories?access_token=secret-token&take=5"
    assert scrub_url(url) == (
        "https://example.tpondemand.com/api/v1/UserStories?access_token=[REDACTED]&take=5"
    )


def test_scrub_url_preserves_other_params() -> None:
    url = "https://x/api/v1/Bugs?format=json&where=(Id eq 1)&access_token=tok"
    scrubbed = scrub_url(url)
    assert "access_token=[REDACTED]" in scrubbed
    assert "format=json" in scrubbed
    assert "(Id eq 1)" in scrubbed
    assert "tok" not in scrubbed.replace("access_token=[REDACTED]", "")


def test_scrub_url_case_insensitive_token_param() -> None:
    assert scrub_url("https://x/?Access_Token=secret") == "https://x/?Access_Token=[REDACTED]"


def test_scrub_url_no_token_unchanged() -> None:
    assert scrub_url("https://x/api/v1/UserStories?take=5") == (
        "https://x/api/v1/UserStories?take=5"
    )


def test_scrub_url_empty_string_passes_through() -> None:
    assert scrub_url("") == ""


# ---------------------------------------------------------------------------
# scrub_message
# ---------------------------------------------------------------------------


def test_scrub_message_redacts_access_token_in_text() -> None:
    msg = "GET https://x/?access_token=supersecret&take=5 failed"
    assert "supersecret" not in scrub_message(msg)
    assert "access_token=[REDACTED]" in scrub_message(msg)


def test_scrub_message_redacts_authorization_basic_header() -> None:
    msg = "Authorization: Basic dXNlcjpwYXNz"
    assert "dXNlcjpwYXNz" not in scrub_message(msg)
    assert "Basic [REDACTED]" in scrub_message(msg)


def test_scrub_message_redacts_authorization_bearer_header() -> None:
    msg = "Authorization: Bearer abc123"
    assert "abc123" not in scrub_message(msg)
    assert "Bearer [REDACTED]" in scrub_message(msg)


def test_scrub_message_leaves_normal_text_unchanged() -> None:
    msg = "request.complete status=200 method=GET"
    assert scrub_message(msg) == msg


def test_scrub_message_empty_string_passes_through() -> None:
    assert scrub_message("") == ""


# ---------------------------------------------------------------------------
# scrub_headers
# ---------------------------------------------------------------------------


def test_scrub_headers_redacts_authorization() -> None:
    scrubbed = scrub_headers({"Authorization": "Basic dXNlcjpwYXNz", "Accept": "application/json"})
    assert scrubbed["Authorization"] == "[REDACTED]"
    assert scrubbed["Accept"] == "application/json"


def test_scrub_headers_redacts_cookie_and_set_cookie() -> None:
    scrubbed = scrub_headers(
        {"Cookie": "session=abc", "Set-Cookie": "session=def", "X-Trace": "123"}
    )
    assert scrubbed["Cookie"] == "[REDACTED]"
    assert scrubbed["Set-Cookie"] == "[REDACTED]"
    assert scrubbed["X-Trace"] == "123"


def test_scrub_headers_case_insensitive() -> None:
    scrubbed = scrub_headers({"authorization": "Bearer xyz"})
    assert scrubbed["authorization"] == "[REDACTED]"


def test_scrub_headers_does_not_mutate_input() -> None:
    original = {"Authorization": "Basic abc"}
    scrub_headers(original)
    assert original["Authorization"] == "Basic abc"


# ---------------------------------------------------------------------------
# ScrubbingFilter
# ---------------------------------------------------------------------------


def test_scrubbing_filter_redacts_record_message() -> None:
    record = logging.LogRecord(
        name="targetprocess",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="GET https://x/?access_token=secret",
        args=(),
        exc_info=None,
    )
    assert ScrubbingFilter().filter(record) is True
    assert "secret" not in record.getMessage()
    assert "access_token=[REDACTED]" in record.getMessage()


def test_scrubbing_filter_redacts_url_extra() -> None:
    record = logging.LogRecord(
        name="targetprocess",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request.start",
        args=(),
        exc_info=None,
    )
    record.url = "https://x/?access_token=secret&take=5"  # type: ignore[attr-defined]
    ScrubbingFilter().filter(record)
    assert "secret" not in record.url  # type: ignore[attr-defined]
    assert "access_token=[REDACTED]" in record.url  # type: ignore[attr-defined]


def test_scrubbing_filter_redacts_headers_extra() -> None:
    record = logging.LogRecord(
        name="targetprocess",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request",
        args=(),
        exc_info=None,
    )
    record.headers = {"Authorization": "Basic abc", "Accept": "application/json"}  # type: ignore[attr-defined]
    ScrubbingFilter().filter(record)
    assert record.headers["Authorization"] == "[REDACTED]"  # type: ignore[attr-defined]
    assert record.headers["Accept"] == "application/json"  # type: ignore[attr-defined]


def test_scrubbing_filter_preformats_percent_args() -> None:
    record = logging.LogRecord(
        name="targetprocess",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="url=%s status=%d",
        args=("https://x/?access_token=secret", 200),
        exc_info=None,
    )
    ScrubbingFilter().filter(record)
    rendered = record.getMessage()
    assert "secret" not in rendered
    assert "access_token=[REDACTED]" in rendered
    assert "status=200" in rendered


# ---------------------------------------------------------------------------
# StructuredJsonFormatter
# ---------------------------------------------------------------------------


def _make_record(msg: str, **extra: Any) -> logging.LogRecord:
    record = logging.LogRecord(
        name="targetprocess",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_structured_json_formatter_emits_json_with_core_keys() -> None:
    record = _make_record("request.complete", method="GET", status=200)
    line = StructuredJsonFormatter().format(record)
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "targetprocess"
    assert payload["msg"] == "request.complete"
    assert payload["method"] == "GET"
    assert payload["status"] == 200
    assert "ts" in payload


def test_structured_json_formatter_includes_request_id_extra() -> None:
    record = _make_record("request.start", request_id="abc123")
    payload = json.loads(StructuredJsonFormatter().format(record))
    assert payload["request_id"] == "abc123"


def test_structured_json_formatter_omits_request_id_when_absent() -> None:
    record = _make_record("request.complete")
    payload = json.loads(StructuredJsonFormatter().format(record))
    assert "request_id" not in payload


def test_structured_json_formatter_serialises_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="targetprocess",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="request.failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    payload = json.loads(StructuredJsonFormatter().format(record))
    assert "ValueError" in payload["exc"]
    assert "boom" in payload["exc"]


# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------


def test_library_logger_has_null_handler_by_default() -> None:
    assert any(isinstance(h, logging.NullHandler) for h in tp_logger.handlers)


def test_library_logger_has_scrubbing_filter_attached() -> None:
    assert any(isinstance(f, ScrubbingFilter) for f in tp_logger.filters)


def test_get_logger_returns_child_under_targetprocess() -> None:
    child = get_logger("transport")
    assert child.name == "targetprocess.transport"
    assert get_logger().name == "targetprocess"


def test_library_logger_does_not_emit_without_handler(caplog: pytest.LogCaptureFixture) -> None:
    # NullHandler swallows; caplog attaches its own handler at propagation.
    # Verify the library logger itself has no stream handler by default.
    assert not any(isinstance(h, logging.StreamHandler) for h in tp_logger.handlers)


# ---------------------------------------------------------------------------
# Request-ID propagation
# ---------------------------------------------------------------------------


def test_new_request_id_is_unique_hex() -> None:
    a = new_request_id()
    b = new_request_id()
    assert a != b
    assert len(a) == 32
    int(a, 16)  # valid hex


def test_current_request_id_none_by_default() -> None:
    assert current_request_id() is None


def test_request_id_context_binds_and_resets() -> None:
    assert current_request_id() is None
    with request_id_context("rid-1"):
        assert current_request_id() == "rid-1"
    assert current_request_id() is None


def test_request_id_context_nesting_restores_outer() -> None:
    with request_id_context("outer"):
        with request_id_context("inner"):
            assert current_request_id() == "inner"
        assert current_request_id() == "outer"
    assert current_request_id() is None


def test_request_id_context_yields_bound_id() -> None:
    with request_id_context("rid-yield") as rid:
        assert rid == "rid-yield"


# ---------------------------------------------------------------------------
# Transport stamps X-Request-ID on every outgoing request
# ---------------------------------------------------------------------------


def _capturing_transport(
    token: str | None = "secret-token",
) -> tuple[HTTPTransport, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    transport = HTTPTransport(domain="example.tpondemand.com", token=token or "secret-token")
    transport._client._transport = httpx.MockTransport(handle)
    return transport, captured


async def test_transport_stamps_request_id_header() -> None:
    transport, captured = _capturing_transport()
    await transport._client.request("GET", "/UserStories")
    assert REQUEST_ID_HEADER in captured[0].headers
    assert len(captured[0].headers[REQUEST_ID_HEADER]) == 32  # generated uuid hex


async def test_transport_uses_context_request_id_when_bound() -> None:
    transport, captured = _capturing_transport()
    with request_id_context("caller-rid"):
        await transport._client.request("GET", "/UserStories")
    assert captured[0].headers[REQUEST_ID_HEADER] == "caller-rid"


async def test_transport_does_not_overwrite_caller_supplied_header() -> None:
    transport, captured = _capturing_transport()
    await transport._client.request(
        "GET", "/UserStories", headers={REQUEST_ID_HEADER: "explicit-rid"}
    )
    assert captured[0].headers[REQUEST_ID_HEADER] == "explicit-rid"


# ---------------------------------------------------------------------------
# RequestHandler emits scrubbed, structured logs and binds request_id
# ---------------------------------------------------------------------------


def _handler_with_mock_transport() -> tuple[RequestHandler, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"Items": [{"Id": 1}], "Next": None})

    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    transport._client._transport = httpx.MockTransport(handle)
    return RequestHandler(transport), captured


async def test_handler_logs_scrubbed_url_without_token(caplog: pytest.LogCaptureFixture) -> None:
    handler, _ = _handler_with_mock_transport()
    caplog.set_level(logging.DEBUG, logger="targetprocess")
    await handler.get("UserStories", 123)
    assert caplog.records  # something was logged
    # No record carries the token value, in either the message or any extra.
    for record in caplog.records:
        assert "secret-token" not in record.getMessage()
        url_extra = getattr(record, "url", None)
        if isinstance(url_extra, str):
            assert "secret-token" not in url_extra


async def test_handler_logs_scrubbed_url_when_token_in_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A URL extra carrying the token is redacted by the scrubbing filter."""
    handler, _ = _handler_with_mock_transport()
    caplog.set_level(logging.DEBUG, logger="targetprocess")
    # Force a record whose url extra carries the token (as if a caller logged
    # the post-auth URL); the filter must redact it before it reaches caplog.
    from targetprocess._observability import logger as tp_log

    with request_id_context("rid"):
        tp_log.debug("request.start", extra={"url": "https://x/?access_token=secret-token&take=5"})
    matching = [r for r in caplog.records if r.getMessage() == "request.start"]
    assert matching
    assert "secret-token" not in matching[-1].url  # type: ignore[attr-defined]
    assert "access_token=[REDACTED]" in matching[-1].url  # type: ignore[attr-defined]


async def test_handler_log_records_carry_request_id(caplog: pytest.LogCaptureFixture) -> None:
    handler, _ = _handler_with_mock_transport()
    caplog.set_level(logging.DEBUG, logger="targetprocess")
    with request_id_context("test-rid"):
        await handler.get("UserStories", 123)
    ids = {getattr(r, "request_id", None) for r in caplog.records}
    assert "test-rid" in ids


async def test_handler_retries_emit_warning_log(caplog: pytest.LogCaptureFixture) -> None:
    statuses = [429, 200]
    state: dict[str, int] = {"i": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        status = statuses[min(state["i"], len(statuses) - 1)]
        state["i"] += 1
        body = {"Id": 1} if status < 400 else {"Error": "HTTP 429"}
        return httpx.Response(status, json=body, headers={"Retry-After": "0"})

    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    transport._client._transport = httpx.MockTransport(handle)

    async def fake_sleep(delay: float) -> None:
        return None

    handler = RequestHandler(transport, sleep=fake_sleep)
    caplog.set_level(logging.WARNING, logger="targetprocess")
    await handler.get("UserStories", 123)
    retry_records = [r for r in caplog.records if r.getMessage() == "request.retry"]
    assert len(retry_records) == 1
    assert getattr(retry_records[0], "status", None) == 429
    assert getattr(retry_records[0], "attempt", None) == 1


async def test_handler_transport_error_emits_error_log(caplog: pytest.LogCaptureFixture) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    transport._client._transport = httpx.MockTransport(handle)
    handler = RequestHandler(transport)
    caplog.set_level(logging.ERROR, logger="targetprocess")
    with pytest.raises(NetworkError):
        await handler.get("UserStories", 123)
    error_records = [r for r in caplog.records if r.getMessage() == "request.transport_error"]
    assert len(error_records) == 1


async def test_handler_propagates_context_request_id_to_header() -> None:
    """The caller-bound request_id reaches the wire as the X-Request-ID header."""
    handler, captured = _handler_with_mock_transport()
    with request_id_context("caller-trace-id"):
        async for _ in handler.list("UserStories", limit=1):
            break
    assert captured[0].headers[REQUEST_ID_HEADER] == "caller-trace-id"


async def test_handler_generates_request_id_when_none_bound() -> None:
    handler, captured = _handler_with_mock_transport()
    await handler.get("UserStories", 123)
    rid = captured[0].headers[REQUEST_ID_HEADER]
    assert rid is not None
    assert len(rid) == 32  # generated uuid hex


# ---------------------------------------------------------------------------
# Scrubbing reaches every path a record can take
# ---------------------------------------------------------------------------

_TOKEN_URL = "https://example.tpondemand.com/api/v1/Bugs?access_token=secret-token&take=1"


def test_child_logger_from_get_logger_scrubs_message(caplog: pytest.LogCaptureFixture) -> None:
    """A child logger scrubs its own records.

    A filter on the parent logger does not run for records propagated from a
    child, so the child needs its own; without it the token reaches handlers
    verbatim.
    """
    caplog.set_level(logging.INFO, logger="targetprocess")
    get_logger("transport").info("fetching %s", _TOKEN_URL)
    (record,) = [r for r in caplog.records if r.name == "targetprocess.transport"]
    assert "secret-token" not in record.getMessage()
    assert "access_token=[REDACTED]" in record.getMessage()


def test_get_logger_does_not_stack_duplicate_filters() -> None:
    first = get_logger("dedup-check")
    get_logger("dedup-check")
    assert sum(isinstance(f, ScrubbingFilter) for f in first.filters) == 1


def test_scrubbing_filter_redacts_arbitrary_string_extras() -> None:
    """Any string extra is scrubbed, not just ``url``/``headers``.

    ``request.transport_error`` logs ``repr(exc)`` under ``error``, and an
    httpx transport error can carry the request URL in its message.
    """
    record = logging.LogRecord(
        "targetprocess", logging.ERROR, __file__, 1, "request.transport_error", None, None
    )
    record.__dict__["error"] = f"ConnectError('failed to connect to {_TOKEN_URL}')"
    ScrubbingFilter().filter(record)
    scrubbed = record.__dict__["error"]
    assert "secret-token" not in scrubbed
    assert "access_token=[REDACTED]" in scrubbed


def test_scrubbing_filter_leaves_standard_record_attributes_alone() -> None:
    record = logging.LogRecord("targetprocess", logging.INFO, "/some/path.py", 7, "hi", None, None)
    ScrubbingFilter().filter(record)
    assert record.pathname == "/some/path.py"
    assert record.levelname == "INFO"


def test_formatter_scrubs_exception_traceback() -> None:
    """The traceback is rendered from ``exc_info`` after the filter has run."""
    try:
        raise httpx.HTTPStatusError(
            f"Client error '401 Unauthorized' for url '{_TOKEN_URL}'",
            request=httpx.Request("GET", _TOKEN_URL),
            response=httpx.Response(401),
        )
    except httpx.HTTPStatusError:
        record = logging.LogRecord(
            "targetprocess", logging.ERROR, __file__, 1, "request failed", None, sys.exc_info()
        )
    payload = json.loads(StructuredJsonFormatter().format(record))
    assert "secret-token" not in payload["exc"]
    assert "access_token=[REDACTED]" in payload["exc"]


async def test_transport_error_log_does_not_leak_token(caplog: pytest.LogCaptureFixture) -> None:
    """End-to-end: a transport error naming the URL is redacted in the log."""

    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed to connect to {request.url}", request=request)

    transport = HTTPTransport(domain="example.tpondemand.com", token="secret-token")
    transport._client._transport = httpx.MockTransport(handle)
    handler = RequestHandler(transport)
    caplog.set_level(logging.ERROR, logger="targetprocess")
    with pytest.raises(NetworkError):
        await handler.get("UserStories", 123)
    (record,) = [r for r in caplog.records if r.getMessage() == "request.transport_error"]
    assert "secret-token" not in getattr(record, "error", "")


# ---------------------------------------------------------------------------
# Request-ID sanitisation
# ---------------------------------------------------------------------------


def test_request_id_context_strips_control_characters() -> None:
    """A CR/LF in an inbound correlation ID must not reach the header."""
    with request_id_context("abc\r\nX-Injected: evil") as bound:
        assert bound == "abcX-Injected: evil"
        assert current_request_id() == bound


def test_request_id_context_falls_back_when_nothing_usable_remains() -> None:
    with request_id_context("\r\n\t") as bound:
        assert bound is not None
        assert len(bound) == 32  # generated uuid hex


def test_request_id_context_length_caps_an_oversized_id() -> None:
    with request_id_context("x" * 500) as bound:
        assert bound == "x" * 200


def test_request_id_context_leaves_a_clean_id_untouched() -> None:
    with request_id_context("caller-trace-id") as bound:
        assert bound == "caller-trace-id"


def test_request_id_context_none_still_clears() -> None:
    with request_id_context("outer"):
        with request_id_context(None) as bound:
            assert bound is None
            assert current_request_id() is None
        assert current_request_id() == "outer"


async def test_control_characters_never_reach_the_wire_header() -> None:
    handler, captured = _handler_with_mock_transport()
    with request_id_context("trace\r\nX-Injected: evil"):
        await handler.get("UserStories", 123)
    stamped = captured[0].headers[REQUEST_ID_HEADER]
    assert "\r" not in stamped
    assert "\n" not in stamped


@pytest.mark.parametrize(
    "key", ["Authorization", "authorization", "Cookie", "Set-Cookie", "Proxy-Authorization"]
)
def test_scrubbing_filter_redacts_secret_named_extras(key: str) -> None:
    """A credential logged as its own extra carries no field name to match on.

    ``extra={"Authorization": "Bearer ..."}`` reaches the filter as a bare
    value, so the free-text patterns cannot recognise it and the key is the
    only signal that it is a secret.
    """
    record = logging.LogRecord("targetprocess", logging.INFO, __file__, 1, "auth", None, None)
    record.__dict__[key] = "Bearer supersecret"
    ScrubbingFilter().filter(record)
    assert record.__dict__[key] == "[REDACTED]"


def test_scrubbing_filter_keeps_non_secret_named_extras() -> None:
    """Redaction is keyed on credential header names, not on every extra."""
    record = logging.LogRecord("targetprocess", logging.INFO, __file__, 1, "req", None, None)
    record.__dict__["method"] = "GET"
    record.__dict__["status"] = 200
    ScrubbingFilter().filter(record)
    assert record.__dict__["method"] == "GET"
    assert record.__dict__["status"] == 200
