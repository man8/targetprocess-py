"""Runtime observability: structured logging, log scrubbing, and request-ID propagation.

This module is the single place where the library's runtime observability
hooks live. Three concerns, each scoped to what a client library should
own (applications own metrics, alerting, error tracking, and deployment
observability - see SPEC.md "Observability"):

* **Structured logging** - a dedicated ``targetprocess`` logger, emitted as
  JSON when a handler is attached, silent (``NullHandler``) by default so
  the library never writes to stderr unless the application opts in.
* **Log scrubbing** - a :class:`ScrubbingFilter` that redacts the
  ``access_token`` query param and ``Authorization`` headers from records
  emitted through this library's own loggers (the ``targetprocess`` logger
  and every child :func:`get_logger` returns), so the token-leak surface
  documented in the README cannot recur through them. Records from other
  libraries - notably ``httpx`` / ``httpcore`` - are outside its reach; see
  SPEC.md "Observability" for what an application should do about those.
* **Correlation-ID propagation** - a ``ContextVar`` request ID, stamped on
  every outgoing request as ``X-Request-ID`` (via the transport's request
  hook) and attachable to every log record, so a caller's request context
  flows end-to-end.
"""

import json
import logging
import re
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

# ContextVar holding the correlation ID bound to the current async context.
_REQUEST_ID: ContextVar[str | None] = ContextVar("targetprocess_request_id", default=None)

# Header name used to propagate the correlation ID on every outgoing request.
REQUEST_ID_HEADER = "X-Request-ID"

_REDACTED = "[REDACTED]"

# access_token=... in a URL query string (TP's token scheme - the token
# travels as a query param, the leak surface the README warns about).
_ACCESS_TOKEN_RE = re.compile(r"(access_token=)[^&\s]+", re.IGNORECASE)
# "Authorization: Basic <tok>" / "Authorization: Bearer <tok>" header values
# that may appear in logged free text (Basic auth is the header alternative).
_AUTH_HEADER_RE = re.compile(
    r"(authorization:\s*)(basic|bearer)\s+[^\s]+",
    re.IGNORECASE,
)
# Header names whose values are credentials and must never be logged verbatim.
_SECRET_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "set-cookie"})

# Attributes the stdlib sets on every LogRecord. Anything outside this set is
# a caller-supplied ``extra`` and is scrubbed before it can reach a handler.
_STD_RECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

# Characters valid in an HTTP header value (RFC 9110 field-value: visible
# ASCII plus space/HTAB). A correlation ID sourced from an inbound request
# is untrusted input, so anything outside this range is stripped before the
# ID is bound - CR/LF in particular would either be rejected by the HTTP
# stack mid-request or, worse, split the header.
_UNSAFE_REQUEST_ID_RE = re.compile(r"[^\x20-\x7e]")
# Upper bound on a bound correlation ID, so an oversized inbound value
# cannot push the request over a server's header-size limit.
_MAX_REQUEST_ID_LEN = 200


def scrub_url(url: str) -> str:
    """Redact the ``access_token`` query parameter from a URL string.

    The TargetProcess token is carried as ``access_token=`` in the request
    URL (TP has no header-borne token scheme), so any URL that reaches a
    log must have that value replaced. Other query params are preserved so
    the URL remains useful for debugging.

    Args:
        url: A URL string that may carry an ``access_token`` query param.

    Returns:
        The URL with any ``access_token`` value replaced by ``[REDACTED]``.
    """
    if not url:
        return url
    return _ACCESS_TOKEN_RE.sub(lambda m: m.group(1) + _REDACTED, url)


def scrub_message(text: str) -> str:
    """Redact known secret surfaces from a free-text log message.

    Redacts ``access_token=`` query params and ``Authorization: Basic|Bearer
    <token>`` header values. The scrub is deliberately narrow to the two
    real secret surfaces this library produces; it does not run a generic
    token-shaped regex, which would risk redacting legitimate entity IDs,
    hashes, or long identifiers that appear in normal log content.

    Args:
        text: The message string to scrub.

    Returns:
        The text with secret values replaced by ``[REDACTED]``.
    """
    if not text:
        return text
    text = _ACCESS_TOKEN_RE.sub(lambda m: m.group(1) + _REDACTED, text)
    text = _AUTH_HEADER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)} {_REDACTED}", text)
    return text


def scrub_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of ``headers`` with credential-bearing values redacted.

    Header names are matched case-insensitively against the known
    credential headers (``Authorization``, ``Proxy-Authorization``,
    ``Cookie``, ``Set-Cookie``). Non-credential headers are preserved so
    the result stays useful for debugging.

    Args:
        headers: A mapping of header names to values.

    Returns:
        A new dict with credential header values replaced by ``[REDACTED]``.
    """
    return {
        name: (_REDACTED if name.lower() in _SECRET_HEADERS else value)
        for name, value in headers.items()
    }


class ScrubbingFilter(logging.Filter):
    """Redact secrets from a log record before it reaches a handler.

    Pre-formats the record's message and scrubs it, then clears ``args`` so
    a downstream formatter re-renders the already-scrubbed string. Also
    scrubs the record's ``extra`` fields - ``url`` via :func:`scrub_url`,
    ``headers`` via :func:`scrub_headers`, and every other string-valued
    extra via :func:`scrub_message` - so a record logged as
    ``logger.info("request", extra={"url": url})`` cannot leak the
    ``access_token`` even when the message format does not include the URL
    directly. Scrubbing every string extra matters because an extra such as
    ``{"error": repr(exc)}`` can carry a request URL the library never
    formatted into the message itself. An extra named for a credential
    header (``{"Authorization": "Bearer ..."}``) is redacted whole: the
    value alone carries no field name for the free-text patterns to match,
    so the key is the only signal that it is a secret.

    A filter attached to a *logger* only sees records logged through that
    logger, not records propagated up from its children, so this filter is
    attached to each logger :func:`get_logger` hands out as well as to the
    ``targetprocess`` parent. An application that wants the same redaction
    applied to records from other libraries (``httpx``, ``httpcore``)
    should attach an instance to its own handler, where every propagated
    record passes through.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API name
        """Scrub the record's message and its extras in place."""
        record.msg = scrub_message(record.getMessage())
        record.args = ()
        for key, value in vars(record).items():
            if key in _STD_RECORD_ATTRS or key.startswith("_"):
                continue
            if key == "url" and isinstance(value, str):
                setattr(record, key, scrub_url(value))
            elif isinstance(value, Mapping) and key == "headers":
                setattr(record, key, scrub_headers(value))
            elif key.lower() in _SECRET_HEADERS:
                # A credential logged as its own extra - extra={"Authorization":
                # "Bearer ..."} - carries the value without the field name, so
                # the free-text patterns cannot recognise it. The key is the
                # only signal there is, so redact wholesale.
                setattr(record, key, _REDACTED)
            elif isinstance(value, str):
                setattr(record, key, scrub_message(value))
        return True


def _attach_scrubbing(target: logging.Logger) -> logging.Logger:
    """Attach a :class:`ScrubbingFilter` to ``target`` unless it has one.

    Idempotent, so repeated :func:`get_logger` calls for the same name do
    not stack duplicate filters onto the logger.
    """
    if not any(isinstance(f, ScrubbingFilter) for f in target.filters):
        target.addFilter(ScrubbingFilter())
    return target


# The library logger. Applications opt in by attaching a handler to this
# logger (or a child via :func:`get_logger`); the NullHandler keeps the
# library silent by default, per the stdlib logging best practice for
# libraries.
logger = logging.getLogger("targetprocess")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
# Scrub records logged through this logger. Children get their own filter
# in get_logger(), because logger-level filters do not run for records that
# merely propagate up from a child.
_attach_scrubbing(logger)


class StructuredJsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line with stable keys.

    Keys: ``ts``, ``level``, ``logger``, ``msg``, and ``request_id`` when
    one is bound to the record, plus any non-reserved ``extra`` fields the
    caller attached. An attached exception (``logger.exception``) is
    serialised under ``exc``.

    Attach this formatter to a handler on the ``targetprocess`` logger to
    get structured output; pair it with :class:`ScrubbingFilter` (already
    attached to the library logger) so secrets are redacted before
    serialisation.
    """

    _RESERVED = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
            "message",
            "asctime",
            "request_id",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        """Return the record serialised as a JSON object on a single line."""
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id is not None:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            # ScrubbingFilter never sees the formatted traceback - it is
            # rendered here, from exc_info - and an httpx status error
            # carries the full request URL (access_token and all) in its
            # message, so scrub it at the point of serialisation.
            payload["exc"] = scrub_message(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the ``targetprocess`` namespace.

    Attach a handler to ``logging.getLogger("targetprocess")`` or the
    returned child to enable output; the library is silent by default.

    The returned logger carries its own :class:`ScrubbingFilter`. A child
    obtained by calling ``logging.getLogger("targetprocess.x")`` directly
    does not, because a filter on the parent logger is not applied to
    records propagated from a child - so use this function rather than the
    stdlib call to keep the redaction guarantee.

    Args:
        name: Optional child name (e.g. ``"transport"``); ``None`` returns
            the ``targetprocess`` logger itself.

    Returns:
        The requested ``logging.Logger``, with scrubbing attached.
    """
    return _attach_scrubbing(
        logging.getLogger("targetprocess" if name is None else f"targetprocess.{name}")
    )


def new_request_id() -> str:
    """Generate a new request ID (UUID4 hex, 32 chars, no dashes)."""
    return uuid.uuid4().hex


def _sanitise_request_id(request_id: str) -> str:
    """Return ``request_id`` reduced to characters safe in a header value.

    The documented use for :func:`request_id_context` is propagating a
    correlation ID that arrived on an inbound request, which makes it
    untrusted input. Left as-is, a CR/LF would either be rejected by the
    HTTP stack - turning every request in that context into a transport
    error - or split the ``X-Request-ID`` header. Characters outside the
    printable-ASCII field-value range are dropped, the result is trimmed
    and length-capped, and an ID with nothing usable left falls back to a
    generated one so the request stays traceable.
    """
    cleaned = _UNSAFE_REQUEST_ID_RE.sub("", request_id).strip()[:_MAX_REQUEST_ID_LEN]
    return cleaned or new_request_id()


def current_request_id() -> str | None:
    """Return the correlation ID bound to the current context, if any."""
    return _REQUEST_ID.get()


@contextmanager
def request_id_context(request_id: str | None) -> Iterator[str | None]:
    """Bind a correlation ID to the current context for the duration of the block.

    The bound ID is read by the transport's request hook to stamp the
    ``X-Request-ID`` header on outgoing requests, and by callers to attach
    to log records. The previous value is restored on exit, so nested
    scopes can override and then return to the outer ID.

    A non-``None`` ID is sanitised to characters valid in a header value
    before it is bound, since the ID commonly originates from an inbound
    request. The sanitised value is what gets bound and yielded, so the
    caller sees exactly what will appear on the wire and in the logs.

    Args:
        request_id: The ID to bind, or ``None`` to clear.

    Yields:
        The bound ``request_id``, sanitised when not ``None``.
    """
    bound = None if request_id is None else _sanitise_request_id(request_id)
    token: Token[str | None] = _REQUEST_ID.set(bound)
    try:
        yield bound
    finally:
        _REQUEST_ID.reset(token)
