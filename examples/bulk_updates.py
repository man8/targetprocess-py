#!/usr/bin/env python
"""Apply an idempotent field update to every Bug in a project (write).

Demonstrates the list-then-update pattern with a READWRITE client: page through
the bugs in a project with ``list(where=...)`` and ``update()`` each one. The
built-in rate limiter paces the requests automatically.

This is a WRITE example, so it guards the destination two independent ways: the
target project must be named on the command line (``--project-id``, required, no
default) AND allow-listed in the ``TP_WRITE_ALLOWED_PROJECT_IDS`` environment
variable, and the write must be confirmed with ``--yes``. The double entry
defends the realistic accident — copy the documented command, edit the id. Point
it at a throwaway/sandbox project, never production; for man8's TargetProcess the
API-testing sandbox project id is ``49938``.

The update sets ``Description`` to a fixed marker, so re-running is idempotent
(it does not accumulate).

Configuration comes from the environment:

- ``TP_DOMAIN`` — instance domain, e.g. ``example.tpondemand.com``
- ``TP_TOKEN``  — API token (sent as the ``access_token`` query parameter)
- ``TP_WRITE_ALLOWED_PROJECT_IDS`` — comma-separated project ids this script may
  write to (e.g. ``49938``)

Run (against the sandbox project):

    export TP_DOMAIN=example.tpondemand.com
    export TP_TOKEN=your-api-token
    export TP_WRITE_ALLOWED_PROJECT_IDS=49938
    python examples/bulk_updates.py --project-id 49938 --limit 10 --yes
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from targetprocess import ClientMode, TargetProcessClient, TargetProcessError

MARKER = "Bulk-updated by the targetprocess-py bulk_updates example."


async def main(project_id: int, limit: int) -> None:
    """Set every in-scope Bug's Description to a fixed marker."""
    async with TargetProcessClient(
        domain=_env("TP_DOMAIN"),
        token=_env("TP_TOKEN"),
        mode=ClientMode.READWRITE,
    ) as client:
        ids = [
            bug.id
            async for bug in client.bugs.list(
                where=f"(Project.Id eq {project_id})",
                limit=limit,
            )
        ]
        if not ids:
            print(f"no bugs found in project {project_id} — nothing to update.")
            return

        for bug_id in ids:
            updated = await client.bugs.update(bug_id, Description=MARKER)
            print(f"updated Bug {updated.id}: {updated.name}")
        print(f"\n{len(ids)} bug(s) updated in project {project_id}.")


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"error: environment variable {name} is required")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-update bugs (write; requires --project-id and --yes)."
    )
    parser.add_argument(
        "--project-id",
        type=int,
        required=True,
        help="target project id — use a sandbox project (man8 sandbox: 49938), never production",
    )
    parser.add_argument("--limit", type=int, default=10, help="max bugs to update (default: 10)")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm the write — required, since this mutates data in --project-id",
    )
    return parser.parse_args()


def _require_write_allowed(project_id: int, yes: bool) -> None:
    """Refuse the write unless the project is allow-listed and confirmed.

    The destination must appear both on the command line (``project_id``) and in
    ``TP_WRITE_ALLOWED_PROJECT_IDS``, and ``--yes`` must be given.
    """
    raw = os.environ.get("TP_WRITE_ALLOWED_PROJECT_IDS", "")
    allowed: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            allowed.add(int(part))
        except ValueError:
            sys.exit(f"error: TP_WRITE_ALLOWED_PROJECT_IDS has a non-integer entry: {part!r}")
    if not allowed:
        sys.exit(
            "refusing to write: set TP_WRITE_ALLOWED_PROJECT_IDS to the sandbox/throwaway "
            "project id(s) you permit (man8 sandbox: 49938), never a production id"
        )
    if project_id not in allowed:
        sys.exit(
            f"refusing to write to project {project_id}: not in "
            f"TP_WRITE_ALLOWED_PROJECT_IDS ({sorted(allowed)})"
        )
    if not yes:
        sys.exit(f"refusing to write to project {project_id} without --yes")


if __name__ == "__main__":
    args = _parse_args()
    _require_write_allowed(args.project_id, args.yes)
    try:
        asyncio.run(main(args.project_id, args.limit))
    except TargetProcessError as exc:
        sys.exit(f"TargetProcess error: {exc}")
