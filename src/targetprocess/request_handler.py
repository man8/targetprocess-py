"""Request handler for TargetProcess API operations."""

import asyncio
import builtins
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, cast
from urllib.parse import urlencode

import httpx
from easylimit import RateLimiter

from targetprocess._entity_types import require_entity_type
from targetprocess._observability import (
    current_request_id,
    logger,
    new_request_id,
    request_id_context,
    scrub_url,
)
from targetprocess.exceptions import APIError, NetworkError, ParseError
from targetprocess.response_parser import ResponseParser
from targetprocess.transport import HTTPTransport

# Retry on 429/5xx: initial attempt + this many retries = 4 requests max.
_MAX_ATTEMPTS = 4
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_FACTOR = 2
_MAX_DELAY_SECONDS = 30.0


class RequestHandler:
    """Handle API requests with rate limiting, retry/backoff, and response parsing.

    Orchestrates:
    - URL construction with query parameters
    - Write-permission enforcement (defense in depth alongside the
      resource layer)
    - Rate limiting (100 requests/minute), applied once per attempt
    - Retry with exponential backoff on 429/5xx, safe methods only
      (GET/HEAD/OPTIONS) - mutating methods are never auto-retried
    - HTTP calls via HTTPTransport
    - Error checking and mapping
    """

    def __init__(
        self,
        transport: HTTPTransport,
        *,
        check_write: Callable[[], None] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize request handler.

        Args:
            transport: HTTPTransport instance for making HTTP calls
            check_write: Optional callback invoked before every write
                (create/update/delete), raising if writes aren't permitted.
                This is the client's readonly-mode check, injected so writes
                are refused here too - not only at the resource layer above.
                Defaults to no check, since RequestHandler is also
                constructed directly in tests without a client.
            sleep: Optional callable used to wait between retries. Defaults
                to ``asyncio.sleep``; injected so retry-backoff tests never
                really sleep.
        """
        self._transport = transport
        self._check_write = check_write
        self._sleep = sleep or asyncio.sleep
        # TargetProcess API limit: ~100 requests per minute
        self._rate_limiter = RateLimiter(limit=100, period=timedelta(minutes=1))

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Make rate-limited HTTP request, retrying 429/5xx on safe methods only.

        Retries up to 3 times (4 attempts total), with exponential backoff
        (0.5s base, factor 2) capped at 30s per delay. A numeric
        ``Retry-After`` header, when present, is honoured in place of the
        computed delay; an HTTP-date value is also honoured (converted to a
        delay relative to now); a header that is neither falls back to the
        exponential schedule. The rate limiter is (re-)acquired once per
        attempt.

        Retry eligibility is method-aware:

        - GET/HEAD/OPTIONS retry on 429 or 5xx - these methods have no side
          effects, so re-sending is always safe.
        - POST/PUT/DELETE never retry, on 429 or 5xx alike. TargetProcess
          documents no guarantee that a 429 response means a mutation was
          not processed, and offers no idempotency keys - so retrying a
          mutating request risks duplicating it. Both status classes
          surface immediately instead; retrying a mutation, if a caller
          knows it to be safe, is the caller's own responsibility.

        A transport-level failure (no response received) is never retried -
        it always raises NetworkError immediately. Once retries are
        exhausted (or a non-retryable status arrives), the last response's
        status is mapped via the normal error handling below, so a
        persistent 429/5xx surfaces as RateLimitError/APIError rather than a
        bespoke retry exception.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: Full URL to request
            **kwargs: Additional arguments for httpx request

        Returns:
            HTTP response

        Raises:
            NetworkError: The request could not be sent (connection error,
                timeout, DNS failure, ...) - no response was received.
            Various exceptions via ResponseParser.parse_error for error status codes
        """
        request_id = current_request_id() or new_request_id()
        response: httpx.Response
        with request_id_context(request_id):
            logger.debug(
                "request.start",
                extra={"method": method, "url": scrub_url(url), "request_id": request_id},
            )
            for attempt in range(_MAX_ATTEMPTS):
                async with self._rate_limiter:
                    try:
                        response = await self._transport._client.request(method, url, **kwargs)
                    except httpx.HTTPError as exc:
                        logger.error(
                            "request.transport_error",
                            extra={"method": method, "error": repr(exc), "request_id": request_id},
                        )
                        raise NetworkError(f"transport failure: {exc!r}") from exc

                retryable = method.upper() in {"GET", "HEAD", "OPTIONS"} and (
                    response.status_code == 429 or response.status_code >= 500
                )
                if not retryable or attempt == _MAX_ATTEMPTS - 1:
                    break
                delay = self._retry_delay(response, attempt)
                logger.warning(
                    "request.retry",
                    extra={
                        "method": method,
                        "status": response.status_code,
                        "attempt": attempt + 1,
                        "delay": delay,
                        "request_id": request_id,
                    },
                )
                await self._sleep(delay)

            # Check for errors and raise appropriate exceptions
            if response.status_code >= 400:
                logger.warning(
                    "request.error",
                    extra={
                        "method": method,
                        "status": response.status_code,
                        "request_id": request_id,
                    },
                )
                ResponseParser.parse_error(response)

            logger.debug(
                "request.complete",
                extra={"method": method, "status": response.status_code, "request_id": request_id},
            )
        return response

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        """Compute the backoff delay before the next retry attempt.

        Honours a ``Retry-After`` header when present, tried in order:
        numeric delta-seconds first, then an HTTP-date (parsed via
        ``email.utils.parsedate_to_datetime`` and converted to a delay
        relative to now); a header that matches neither format falls back to
        the exponential schedule, as does a missing header. A negative or
        past-due delay is floored at 0s. Every delay is capped at 30s.
        """
        retry_after = response.headers.get("Retry-After")
        delay: float | None = None
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                try:
                    retry_date = parsedate_to_datetime(retry_after)
                    if retry_date.tzinfo is None:
                        retry_date = retry_date.replace(tzinfo=UTC)
                    delay = (retry_date - datetime.now(UTC)).total_seconds()
                except (ValueError, TypeError):
                    delay = None
        if delay is None:
            delay = _BACKOFF_BASE_SECONDS * _BACKOFF_FACTOR**attempt
        return min(max(delay, 0.0), _MAX_DELAY_SECONDS)

    @staticmethod
    def _shaping_params(
        *,
        include: list[str] | None,
        exclude: list[str] | None,
        result_include: list[str] | None,
        append: list[str] | None,
        innertake: int | None,
    ) -> dict[str, str]:
        """Build the response-shaping query params shared by ``get`` and ``list``.

        Field lists render in TP's bracketed form (``include=[Field1,Field2]``);
        ``innertake`` renders as a plain integer.

        Raises:
            ValueError: ``innertake`` is negative.
        """
        params: dict[str, str] = {}
        for name, fields in (
            ("include", include),
            ("exclude", exclude),
            ("resultInclude", result_include),
            ("append", append),
        ):
            if fields:
                params[name] = f"[{','.join(fields)}]"
        if innertake is not None:
            if innertake < 0:
                raise ValueError(f"innertake must be >= 0 (got {innertake})")
            params["innertake"] = str(innertake)
        return params

    async def get(
        self,
        entity_type: str,
        id: int,
        include: list[str] | None = None,
        *,
        exclude: list[str] | None = None,
        result_include: list[str] | None = None,
        append: list[str] | None = None,
        innertake: int | None = None,
    ) -> dict[str, Any]:
        """Get single entity by ID.

        Args:
            entity_type: TP entity type (e.g., "UserStories", "Bugs")
            id: Entity ID
            include: Optional list of fields to include
            exclude: Optional list of fields to exclude from the response
                (server-side; the complement of ``include``)
            result_include: Optional list of fields to restrict the response
                to - server-side payload narrowing (``resultInclude=``)
            append: Optional list of calculated fields to append
                (e.g. ``["Tasks-Count"]``)
            innertake: Optional bound on the size of nested collections
                hydrated via ``include``

        Returns:
            Raw entity data dict

        Raises:
            ValueError: ``innertake`` is negative.

        Example:
            >>> data = await handler.get("UserStories", 123, include=["Name", "EntityState"])
        """
        require_entity_type(entity_type)
        # Build URL
        url = f"{self._transport.base_url}/{entity_type}/{id}"

        # Build query parameters
        params = {"format": "json"}
        params.update(
            self._shaping_params(
                include=include,
                exclude=exclude,
                result_include=result_include,
                append=append,
                innertake=innertake,
            )
        )

        # Add query string to URL
        url = f"{url}?{urlencode(params)}"

        # Make request
        response = await self._request("GET", url)
        return cast(dict[str, Any], response.json())

    @staticmethod
    def _list_params(
        *,
        where: str | None,
        include: list[str] | None,
        exclude: list[str] | None,
        result_include: list[str] | None,
        append: list[str] | None,
        innertake: int | None,
        order_by: str | None,
        order_by_desc: str | None,
        skip: int | None,
        limit: int | None,
        page_size: int,
    ) -> dict[str, str]:
        """Validate and build the first-request query params for ``list``.

        Raises:
            ValueError: Both ``order_by`` and ``order_by_desc`` were passed
                (each direction was verified individually against the live
                API; their combination is undefined, so it is refused rather
                than sent), ``skip`` is negative, or ``innertake`` is
                negative.
        """
        if order_by is not None and order_by_desc is not None:
            raise ValueError("pass at most one of order_by / order_by_desc, not both")
        if skip is not None and skip < 0:
            raise ValueError(f"skip must be >= 0 (got {skip})")
        params: dict[str, str] = {
            "format": "json",
            "take": str(min(page_size, limit) if limit else page_size),
        }
        if where:
            params["where"] = where
        if order_by:
            params["orderBy"] = order_by
        if order_by_desc:
            params["orderByDesc"] = order_by_desc
        if skip is not None:
            params["skip"] = str(skip)
        params.update(
            RequestHandler._shaping_params(
                include=include,
                exclude=exclude,
                result_include=result_include,
                append=append,
                innertake=innertake,
            )
        )
        return params

    async def list(
        self,
        entity_type: str,
        *,
        where: str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        result_include: list[str] | None = None,
        append: list[str] | None = None,
        innertake: int | None = None,
        order_by: str | None = None,
        order_by_desc: str | None = None,
        skip: int | None = None,
        limit: int | None = None,
        page_size: int = 25,
    ) -> AsyncIterator[dict[str, Any]]:
        """List entities with lazy pagination.

        Yields entities one at a time, fetching pages as needed. Pagination
        follows the server-provided ``Next`` URL verbatim - never recomputing
        ``skip`` locally - so short pages never silently drop items. Before
        it is requested, each ``Next`` URL is checked against the
        transport's base URL (see ``_check_next_url_host``) so a malicious
        or misconfigured continuation URL can never redirect the request
        (and its ``access_token``) to an unexpected host.

        ``skip`` is a deliberate opt-in: it offsets where iteration *starts*
        (sent on the first request only), after which pagination still
        follows ``Next`` verbatim. The default remains the forward-only
        ``Next`` walk from offset 0 - offsets are never recomputed locally.

        Args:
            entity_type: TP entity type (e.g., "UserStories", "Bugs")
            where: TP `where=` filter expression, passed through verbatim
            include: Optional list of fields to include
            exclude: Optional list of fields to exclude from the response
                (server-side; the complement of ``include``)
            result_include: Optional list of fields to restrict each item
                to - server-side payload narrowing (``resultInclude=``)
            append: Optional list of calculated fields to append
                (e.g. ``["Tasks-Count"]``)
            innertake: Optional bound on the size of nested collections
                hydrated via ``include``
            order_by: Optional field to sort by, ascending, server-side
                (``orderBy=``); mutually exclusive with ``order_by_desc``
            order_by_desc: Optional field to sort by, descending, server-side
                (``orderByDesc=``); mutually exclusive with ``order_by``
            skip: Optional server-side offset before the first yielded item
                (opt-in - see above)
            limit: Maximum TOTAL items to yield across all pages (None = unbounded)
            page_size: Page size for each underlying request (`take=`)

        Yields:
            Raw entity data dicts

        Raises:
            ValueError: Both ``order_by`` and ``order_by_desc`` were passed,
                ``skip`` is negative, or ``innertake`` is negative. Raised
                when iteration begins (this is an async generator), not at
                the call itself.

        Example:
            >>> async for item in handler.list(
            ...     "UserStories", where="(EntityState.IsFinal eq 'false')"
            ... ):
            ...     process(item)
        """
        require_entity_type(entity_type)
        # Validate-and-build before the limit short-circuit, so invalid
        # arguments raise rather than vanishing behind an empty iteration.
        params = self._list_params(
            where=where,
            include=include,
            exclude=exclude,
            result_include=result_include,
            append=append,
            innertake=innertake,
            order_by=order_by,
            order_by_desc=order_by_desc,
            skip=skip,
            limit=limit,
            page_size=page_size,
        )
        if limit is not None and limit <= 0:
            return

        yielded = 0
        url: str | None = f"/{entity_type}"
        first = True
        while url is not None:
            response = await self._request("GET", url, params=params if first else None)
            first = False
            data = response.json()
            items = data.get("Items") or []
            for item in items:
                yield item
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            next_url = data.get("Next")
            if next_url is not None:
                self._check_next_url_host(next_url)
            url = next_url

    def _check_next_url_host(self, next_url: str) -> None:
        """Guard against a server-provided ``Next`` URL redirecting off-host.

        ``Next`` is server-controlled, and every request sent through this
        handler's transport carries the ``access_token`` (merged in at send
        time - see ``HTTPTransport``/``_QueryTokenAuth`` - regardless of
        destination host). Blindly following an absolute ``Next`` to an
        unexpected host would leak the token there (SSRF), so the resolved
        scheme/host/port must match the transport's base URL exactly. A
        relative ``Next`` resolves against the base URL and so matches - and
        passes - by construction.

        Raises:
            NetworkError: The resolved URL's scheme, host, or port differs
                from the transport's base URL.
        """
        base = self._transport._client.base_url
        resolved = base.join(next_url)
        if (resolved.scheme, resolved.host, resolved.port) != (
            base.scheme,
            base.host,
            base.port,
        ):
            raise NetworkError(
                f"refusing to follow Next URL to unexpected host {resolved.host!r} "
                f"(expected {base.host!r})"
            )

    async def create(self, entity_type: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Create new entity.

        Args:
            entity_type: TP entity type (e.g., "UserStories", "Bugs")
            fields: Entity field values

        Returns:
            Created entity data dict

        Example:
            >>> data = await handler.create("UserStories", {
            ...     "Name": "New Story",
            ...     "Project": {"Id": 42}
            ... })
        """
        if self._check_write is not None:
            self._check_write()
        require_entity_type(entity_type)
        url = f"{self._transport.base_url}/{entity_type}?format=json"
        response = await self._request("POST", url, json=fields)
        return cast(dict[str, Any], response.json())

    async def update(self, entity_type: str, id: int, fields: dict[str, Any]) -> dict[str, Any]:
        """Update existing entity.

        Args:
            entity_type: TP entity type (e.g., "UserStories", "Bugs")
            id: Entity ID
            fields: Entity field values to update

        Returns:
            Updated entity data dict

        Example:
            >>> data = await handler.update("UserStories", 123, {
            ...     "Name": "Updated Name"
            ... })
        """
        if self._check_write is not None:
            self._check_write()
        require_entity_type(entity_type)
        url = f"{self._transport.base_url}/{entity_type}/{id}?format=json"
        response = await self._request("POST", url, json=fields)
        return cast(dict[str, Any], response.json())

    # Return annotations on methods defined after ``list`` above must spell
    # ``builtins.list``: in class scope the method name shadows the builtin.
    async def bulk(
        self, entity_type: str, items: Sequence[dict[str, Any]]
    ) -> builtins.list[dict[str, Any]]:
        """Create and/or update several entities in one request.

        TargetProcess exposes a per-collection bulk endpoint -
        ``POST /api/v1/{collection}/bulk`` taking a JSON array of entity
        objects. An object carrying an ``Id`` updates that entity; an object
        without one creates a new entity; one request may mix both (vendor
        API reference - the UserStories, Projects, Features, Users and
        Requesters pages all document the endpoint this way).

        Like every mutating request, a bulk request is write-gated and never
        auto-retried (see ``_request``): a 429 or 5xx surfaces immediately.
        The vendor documents neither the response body's shape nor whether a
        failed bulk request is atomic, so on an error a caller must not
        assume all-or-nothing behaviour - some of the array may have been
        applied.

        An empty ``items`` returns ``[]`` without making a network request;
        the write gate still runs first, so a readonly client is refused
        even for an empty batch.

        Args:
            entity_type: TP entity type (e.g., "UserStories", "Bugs")
            items: Entity field dicts, one per entity to create or update

        Returns:
            The response's entity data dicts. The response body shape is
            not vendor-documented, so both plausible envelopes are
            accepted: a bare JSON array, or an object wrapping the array
            as ``Items``.

        Raises:
            ReadOnlyViolation: The client is in readonly mode.
            ParseError: The response body was neither a JSON array nor an
                ``Items``-wrapped one, or any element of it was not an
                object.
            Other exceptions as for any POST (see ``_request``).

        Example:
            >>> created = await handler.bulk(
            ...     "UserStories",
            ...     [
            ...         {"Name": "First", "Project": {"Id": 2}},
            ...         {"Name": "Second", "Project": {"Id": 2}},
            ...     ],
            ... )
        """
        if self._check_write is not None:
            self._check_write()
        require_entity_type(entity_type)
        if not items:
            return []
        url = f"{self._transport.base_url}/{entity_type}/bulk?format=json"
        response = await self._request("POST", url, json=list(items))
        data: Any = response.json()
        items_out: Any = data.get("Items") if isinstance(data, dict) else data
        if isinstance(items_out, list) and all(isinstance(item, dict) for item in items_out):
            return cast(list[dict[str, Any]], items_out)
        raise ParseError(
            "bulk response was neither a JSON array of objects nor an "
            f"'Items'-wrapped array of objects (got {type(data).__name__})"
        )

    async def download_file(self, path: str) -> bytes:
        """GET an instance-root path and return the raw response body.

        Attachment bytes are served from the application root (e.g.
        ``/Attachment.aspx?AttachmentID=1234`` - the ``Uri`` an Attachment
        record carries), not from under ``/api/v1``, so the URL is built from
        the transport's domain rather than its API base URL. The transport's
        auth applies as on any other request; note TargetProcess documents
        file downloads against Basic auth ("You can't use REST API Token to
        download attached file so far" - vendor guide), so a token-auth
        client may be refused or redirected here.

        Args:
            path: Instance-root path - must start with exactly one ``/``
                (e.g. ``/Attachment.aspx?AttachmentID=1234``); anything else
                raises ``ValueError`` (see ``_require_instance_path``)

        Returns:
            Raw response body bytes

        Raises:
            ValueError: ``path`` is not an absolute instance-root path.
            APIError: The server answered with a redirect (3xx). Redirects
                are never followed - the auth credential must not travel to
                a host this handler did not choose - and an attachment
                download that redirects (typically to a login page, for an
                auth scheme the endpoint does not accept) has not returned
                the file, so returning its empty body would silently hand
                back nothing.
            Other exceptions as for any GET (see ``_request``).
        """
        self._require_instance_path(path)
        url = f"https://{self._transport.domain}{path}"
        response = await self._request("GET", url)
        self._reject_redirect(response, "download")
        return response.content

    async def upload_file(
        self,
        path: str,
        *,
        data: dict[str, Any],
        files: dict[str, Any],
    ) -> str:
        """POST multipart/form-data to an instance-root path.

        TargetProcess uploads attachments outside the JSON entity API:
        ``POST /UploadFile.ashx`` with ``Content-Type: multipart/form-data``,
        a ``generalid`` form field naming the target entity and the file
        content as a ``file`` part (vendor-documented wire shape). The
        response body is returned verbatim - TargetProcess does not document
        its shape, so this layer does not interpret it.

        Like every mutating request, the upload is write-gated and never
        auto-retried.

        Args:
            path: Instance-root path - must start with exactly one ``/``
                (e.g. ``/UploadFile.ashx``); anything else raises
                ``ValueError`` (see ``_require_instance_path``)
            data: Plain form fields (e.g. ``{"generalid": "42"}``)
            files: File parts, in httpx's ``files=`` shape
                (e.g. ``{"file": (filename, content, mime_type)}``)

        Returns:
            The response body text, verbatim

        Raises:
            ValueError: ``path`` is not an absolute instance-root path.
            ReadOnlyViolation: The client is in readonly mode.
            APIError: The server answered with a redirect (3xx) - see
                ``download_file`` for why redirects are rejected.
            Other exceptions as for any POST (see ``_request``).
        """
        if self._check_write is not None:
            self._check_write()
        self._require_instance_path(path)
        url = f"https://{self._transport.domain}{path}"
        response = await self._request("POST", url, data=data, files=files)
        self._reject_redirect(response, "upload")
        return response.text

    @staticmethod
    def _require_instance_path(path: str) -> None:
        """Refuse a path that could re-anchor the request's host.

        Instance-root paths are interpolated directly after the domain in
        ``https://<domain><path>``, so anything but a single leading slash
        can reinterpret the URL's authority - ``@attacker.example/f`` turns
        the real domain into userinfo and sends the request (credential
        included) to ``attacker.example``, any other slash-less prefix
        extends the hostname, and a ``//`` prefix is the protocol-relative
        shape of the same trick. ``download_file`` can be fed a
        server-supplied value (an Attachment record's ``Uri``), so this is
        enforced, not just documented: the path must be absolute from the
        instance root, meaning exactly one leading slash.

        Raises:
            ValueError: ``path`` does not start with exactly one ``/``.
        """
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError(
                "instance-root path must start with exactly one leading '/' "
                f"(got {path!r}) - anything else would re-anchor the request "
                "host and leak the credential to it"
            )

    @staticmethod
    def _reject_redirect(response: httpx.Response, operation: str) -> None:
        """Refuse a 3xx response on a file operation.

        Redirects are not followed anywhere in this handler (following one
        would carry the auth credential to a URL the server chose), so on a
        file operation a 3xx means the file was not transferred - surface
        that rather than letting an empty body read as success.
        """
        if 300 <= response.status_code < 400:
            raise APIError(
                f"file {operation} answered with a redirect "
                f"(HTTP {response.status_code}); redirects are not followed. "
                "TargetProcess serves file endpoints against Basic auth - a "
                "token-authenticated client is typically redirected to the "
                "login page here.",
                status_code=response.status_code,
            )

    async def delete(self, entity_type: str, id: int) -> None:
        """Delete entity.

        Args:
            entity_type: TP entity type (e.g., "UserStories", "Bugs")
            id: Entity ID

        Example:
            >>> await handler.delete("UserStories", 123)
        """
        if self._check_write is not None:
            self._check_write()
        require_entity_type(entity_type)
        url = f"{self._transport.base_url}/{entity_type}/{id}?format=json"
        await self._request("DELETE", url)
