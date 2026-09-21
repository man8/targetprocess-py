# Observability

What this library emits at runtime, and the readiness signals it deliberately
leaves to the application that embeds it. Split out of [SPEC.md](../SPEC.md),
which carries the behavioural contract itself and links here.

Runtime observability lives in `targetprocess_py/_observability.py` and is
scoped to what a *library* should own. The application that embeds the
library owns the rest (metrics, alerting, error tracking, deployment
observability, product analytics) - it has the deployment context a
library cannot assume.

## Implemented signals

- **Structured logging.** A dedicated `logging.getLogger("targetprocess_py")`
  with a `NullHandler` by default (silent unless the application attaches a
  handler). `StructuredJsonFormatter` emits one JSON line per record
  (`ts`, `level`, `logger`, `msg`, `request_id`, plus caller extras).
  `get_logger("name")` returns a child under the `targetprocess_py` namespace.
  `RequestHandler._request` emits structured `request.start` /
  `request.complete` / `request.retry` / `request.error` /
  `request.transport_error` records.
- **Log scrubbing.** `ScrubbingFilter` redacts the `access_token` query
  param and `Authorization: Basic|Bearer` header values from the records
  this library emits. It is attached to the `targetprocess_py` logger and to
  every child `get_logger()` returns - both, because a filter on a logger
  runs only for records logged *through* that logger, not for records
  propagated up from a child. It pre-formats and redacts the message, the
  `url` extra, the `headers` extra, and every other string-valued extra
  (an extra such as `{"error": repr(exc)}` can carry a request URL the
  message never mentions); `StructuredJsonFormatter` additionally scrubs
  the formatted traceback, which is rendered from `exc_info` after the
  filter has run. `scrub_url`, `scrub_message`, and `scrub_headers` are the
  underlying helpers. The scrub is deliberately
  narrow to the two real secret surfaces this library produces (TP carries
  the token as a query param, and Basic auth is the header alternative); it
  does not run a generic token-shaped regex, which would redact legitimate
  entity IDs, hashes, and long identifiers that appear in normal log
  content. This closes the token-leak surface the README already warns about
  for httpx request-URL logging, *in this library's own records*. The filter
  cannot reach records emitted by other libraries - `httpx` and `httpcore`
  log their own request URLs - nor a logger obtained by calling
  `logging.getLogger("targetprocess_py.x")` directly instead of via
  `get_logger()`. An application that wants blanket redaction should attach
  a `ScrubbingFilter()` instance to its own handler, which every propagated
  record passes through whatever logger produced it.
- **Distributed tracing (correlation-ID propagation).** A `ContextVar`
  request ID is stamped on every outgoing request as an `X-Request-ID`
  header by the transport's request event hook, and bound to every log
  record `RequestHandler` emits. `new_request_id()` generates an ID,
  `current_request_id()` reads the bound one, and
  `request_id_context(rid)` binds one for a scope (so a caller's request
  context flows into both the wire header and the library's logs). A
  caller-supplied `X-Request-ID` header is never overwritten. When no ID is
  bound, the transport generates one so every request is still traceable.
  Because the bound ID typically originates from an inbound request, it is
  untrusted input: `request_id_context` strips characters outside the
  printable-ASCII header field-value range, trims and length-caps the
  result, and falls back to a generated ID if nothing usable remains - so a
  CR/LF cannot split the header or fail every request in that scope.

## Won't-fix (not applicable to a client library)

The remaining Debugging & Observability readiness signals are deliberately
not implemented, because they are deployment/organisation concerns owned by
the application that embeds this library, not by the library itself. A
library that shipped its own Sentry, alerting, or product-analytics
integration would impose a specific vendor and deployment shape on every
caller - the opposite of the minimal-dependency posture this library takes
(`httpx`, `pydantic`, `easylimit`, and the stdlib only).

- **metrics_collection** - won't-fix. A library has no global runtime to
  sample; metrics belong to the embedding application, which already has a
  metrics backend. `RequestHandler`'s structured logs (`status`,
  `attempt`, `delay`, `request_id`) are the lightweight, vendor-neutral
  substrate an application can count into its own metrics.
- **error_tracking_contextualized** - won't-fix. Bundling Sentry/Bugsnag
  would add a hard dependency and a vendor choice the library should not
  make. Callers catch `TargetProcessError` (or a subclass) and forward it
  to whatever error tracker they run; the `request_id` on the log records
  gives the correlation context.
- **alerting_configured** - won't-fix. Alerting is a property of an
  operated system, not a library. There is no deployment here to alert on.
- **deployment_observability** - won't-fix. The library has no deployment
  pipeline, runtime, or infrastructure to observe.
- **product_analytics_instrumentation** - won't-fix. A library does not
  have end-users to instrument; product analytics are the application's
  responsibility.
- **error_to_insight_pipeline** - won't-fix. This is an aggregation
  concern over an organisation's error/metrics stores; it operates on the
  application's observability backends, not on a library's emit site.
