#!/usr/bin/env python3
"""Exercise every read accessor once against a live TargetProcess instance.

The recorded integration suite proves the client parses what TP *sent on the
day a cassette was recorded*. This proves it still parses what TP sends now -
the check a cassette cannot make, and the one that catches an instance whose
fields, permissions or API version have moved since.

Read-only by construction: the client is built in ``READONLY`` mode, so a
write is refused before any request is sent, and the run ends by asserting
that refusal actually fires. Nothing here creates, updates or deletes
anything; the write path is exercised against the sandbox project by
``tests/integration/test_live_readwrite_surfaces.py``, never from here.

**Not a CI gate**, and deliberately not wired into one: it needs a live
instance and a real token, neither of which CI has. Run it by hand when a
change touches parsing, when adopting a new instance, or before a release.

Credentials come from ``TP_API_TOKEN`` / ``TP_BASE_URL`` in the environment,
falling back to ``~/.config/targetprocess/.env``; there is no default host,
so an unconfigured run stops rather than pointing somewhere unintended.

The output is deliberately identifiers and counts only - never a name, a
login, an instance host or any free text - so it can be pasted into an issue
or a pull request unedited. The host is replaced wholesale rather than by its
tenant label (an instance need not be on the vendor's domain, and the
remainder would name the customer just as plainly), and a failure reports its
exception *type* without the message, because a TargetProcess validation
error quotes the user and project it is about.

Usage:
    uv run python scripts/live_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from targetprocess import ClientMode, ReadOnlyViolation, TargetProcessClient

ENV_FILE = Path.home() / ".config" / "targetprocess" / ".env"

# How many records each listing asks for. Small on purpose: this is a shape
# check, not a load test, and a live instance's owner should not pay for a
# full scan to learn that parsing works.
SAMPLE = 3

# Stands in for the configured host wherever this script prints anything.
_MASKED_HOST = "<masked>"


def load_credentials() -> tuple[str, str]:
    """Resolve (domain, token) from the environment, then the canonical env file.

    Returns:
        The instance host and the API token.

    Raises:
        SystemExit: Either value is missing. There is no default host - a
            smoke run that silently picked one could hit an instance the
            caller did not mean to touch.
    """
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, value = stripped.split("=", 1)
                env[key.strip()] = value.strip().strip("\"'")

    token = os.environ.get("TP_API_TOKEN") or env.get("TP_API_TOKEN")
    base_url = os.environ.get("TP_BASE_URL") or env.get("TP_BASE_URL")
    if not token or not base_url:
        raise SystemExit(
            f"TP_API_TOKEN and TP_BASE_URL must be set in the environment or {ENV_FILE}"
        )
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    return (parsed.netloc or base_url).lower(), token


class Smoke:
    """Runs the checks and tallies the failures.

    A class rather than loose functions so a check's failure is recorded and
    the run continues: one broken accessor should report every *other*
    accessor's state in the same pass, not hide it behind the first
    traceback.
    """

    def __init__(self) -> None:
        """Start with no failures recorded."""
        self.failures: list[str] = []

    async def check(self, name: str, run: Callable[[], Awaitable[str]]) -> None:
        """Run one named check, recording rather than raising on failure."""
        try:
            print(f"PASS {name}: {await run()}")
        except Exception as exc:  # noqa: BLE001 - a smoke run reports, never aborts
            self.failures.append(name)
            # The type only: a TargetProcess error message quotes the user,
            # project or card it is about, and this output is meant to be
            # shareable. Re-run the one accessor by hand for the detail.
            print(f"FAIL {name}: {type(exc).__name__}")

    async def collect(self, name: str, source: Any) -> list[int]:
        """Run a listing as a check *and* keep its Ids for later checks to use.

        Two accessors feed the ones after them - a story Id scopes the join
        listings, an attachment Id is what ``download`` fetches - so their
        results have to escape the check that ran them. Running them as
        checks rather than bare calls is what keeps an unreachable instance
        from aborting the whole run on its first listing, reporting nothing
        about the accessors after it.
        """
        ids: list[int] = []

        async def run() -> str:
            nonlocal ids
            ids = await _ids(source)
            return await _summary(ids)

        await self.check(name, run)
        return ids


async def _ids(source: Any) -> list[int]:
    """Collect the Ids from an async listing, which is all this script reports."""
    return [item.id async for item in source]


async def run_checks(client: TargetProcessClient, smoke: Smoke) -> None:
    """Exercise every read accessor once, plus the readonly refusal."""
    stories = await smoke.collect("user_stories.list", client.user_stories.list(limit=SAMPLE))

    # Every other typed manager whose listing needs no argument, driven from
    # one list so adding a resource to the client means adding a name here
    # rather than another near-identical block.
    for name in (
        "bugs",
        "tasks",
        "features",
        "epics",
        "requests",
        "test_cases",
        "times",
        "projects",
        "teams",
        "users",
        "releases",
        "iterations",
        "team_iterations",
        "entity_states",
        "priorities",
        "severities",
        "processes",
        "workflows",
        "entity_types",
        "terms",
        "custom_fields",
        "custom_activities",
        "custom_rules",
    ):
        resource = getattr(client, name)
        await smoke.check(f"{name}.list", lambda r=resource: _summarise(r.list(limit=SAMPLE)))

    scoped = [
        "user_stories.get(include=Project)",
        "comments.list(scoped)",
        "assignments.list(scoped)",
        "team_assignments.list(scoped)",
        "role_efforts.list(scoped)",
    ]
    if not stories:
        # Named rather than silent: these scoped listings are the only
        # *live* read coverage these surfaces get - a cassette pins what TP
        # answered on recording day, not what it answers now - and a run
        # that skipped them while printing RESULT: PASS would hide that.
        for name in scoped:
            print(f"SKIP {name}: no story to scope the listing by")
    else:
        story_id = stories[0]
        await smoke.check(
            "user_stories.get(include=Project)",
            lambda: _one(client.user_stories.get(story_id, include=["Project"])),
        )
        await smoke.check(
            "comments.list(scoped)",
            lambda: _summarise(client.comments.list(where=f"General.Id eq {story_id}")),
        )
        await smoke.check(
            "assignments.list(scoped)",
            lambda: _summarise(
                client.assignments.list(
                    where=f"Assignable.Id eq {story_id}", include=["GeneralUser", "Role"]
                )
            ),
        )
        await smoke.check(
            "team_assignments.list(scoped)",
            lambda: _summarise(
                client.team_assignments.list(where=f"Assignable.Id eq {story_id}", include=["Team"])
            ),
        )
        await smoke.check(
            "role_efforts.list(scoped)",
            lambda: _summarise(
                client.role_efforts.list(where=f"Assignable.Id eq {story_id}", include=["Role"])
            ),
        )

    # Instance-wide lookups, listed whole rather than sampled - each is a
    # handful of records, and their completeness is the point.
    await smoke.check("roles.list", lambda: _summarise(client.roles.list()))
    await smoke.check("relation_types.list", lambda: _summarise(client.relation_types.list()))
    await smoke.check(
        "relations.list",
        lambda: _summarise(
            client.relations.list(limit=SAMPLE, include=["Master", "Slave", "RelationType"])
        ),
    )
    await smoke.check(
        "entities.list('Comment')",
        lambda: _summarise(client.entities.list("Comment", limit=SAMPLE)),
    )

    attachments = await smoke.collect("attachments.list", client.attachments.list(limit=1))
    if attachments:
        await smoke.check("attachments.download", lambda: _downloaded(client, attachments[0]))
    else:
        print("SKIP attachments.download: the instance has no attachment to fetch")

    await smoke.check("readonly refusal", lambda: _refuses_write(client))


async def _summarise(source: Any) -> str:
    """Render a listing as a count and its Ids."""
    return await _summary(await _ids(source))


async def _summary(ids: list[int]) -> str:
    """Render already-collected Ids. Ids only - never a name or any free text."""
    return f"{len(ids)} record(s), ids={ids}"


async def _one(fetched: Awaitable[Any]) -> str:
    """Render a single fetched entity as its Id and type."""
    entity = await fetched
    return f"id={entity.id} type={entity.resource_type}"


async def _downloaded(client: TargetProcessClient, attachment_id: int) -> str:
    """Fetch an attachment's bytes, reporting only how many arrived.

    The byte count is the whole result on purpose: the file belongs to the
    instance's owner, and this script's output is meant to be shareable.
    """
    content = await client.attachments.download(attachment_id)
    return f"attachment {attachment_id}: {len(content)} bytes"


async def _refuses_write(client: TargetProcessClient) -> str:
    """Assert a write is refused before any request leaves the process.

    Last rather than first, so it also proves the refusal still holds after
    the whole read surface has been exercised on this client.
    """
    try:
        await client.user_stories.create(Name="live_smoke must never create this")
    except ReadOnlyViolation:
        return "create() raised ReadOnlyViolation, as a READONLY client must"
    raise AssertionError("create() was not refused by a READONLY client")


async def main() -> int:
    """Run every check and report, returning a process exit status."""
    domain, token = load_credentials()
    smoke = Smoke()
    # The whole host, not merely its tenant label: an instance need not be on
    # the vendor's domain, and "<masked>.customer.internal" would name the
    # customer as plainly as the tenant label does. The operator already knows
    # which instance they configured; nobody they share this output with needs
    # to. This is the only place the host could reach the output - a failed
    # check prints its exception type without the message, which is where a
    # host would otherwise surface.
    print(f"instance: {_MASKED_HOST}")
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READONLY) as client:
        await run_checks(client, smoke)

    if smoke.failures:
        print(f"\nRESULT: FAIL ({len(smoke.failures)}): {', '.join(smoke.failures)}")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
