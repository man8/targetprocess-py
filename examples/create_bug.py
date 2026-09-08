#!/usr/bin/env python
"""Create a single Bug in a TargetProcess project (write).

Demonstrates a READWRITE client and ``create()``. This is a WRITE example, so
it guards the destination two independent ways: the target project must be
named on the command line (``--project-id``, required, no default) AND
allow-listed in the ``TP_WRITE_ALLOWED_PROJECT_IDS`` environment variable, and
the write must be confirmed with ``--yes``. The double entry defends the
realistic accident — copy the documented command, edit the id — that a lone
confirmation flag does not. Point it at a throwaway/sandbox project, never
production; for man8's TargetProcess the API-testing sandbox project id is
``49938``.

Configuration comes from the environment:

- ``TP_DOMAIN`` — instance domain, e.g. ``example.tpondemand.com``
- ``TP_TOKEN``  — API token (sent as the ``access_token`` query parameter)
- ``TP_WRITE_ALLOWED_PROJECT_IDS`` — comma-separated project ids this script may
  write to (e.g. ``49938``)

Run (against the sandbox project):

    export TP_DOMAIN=example.tpondemand.com
    export TP_TOKEN=your-api-token
    export TP_WRITE_ALLOWED_PROJECT_IDS=49938
    python examples/create_bug.py --project-id 49938 --name "Example bug" --yes
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from targetprocess import ClientMode, TargetProcessClient, TargetProcessError


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"error: environment variable {name} is required")
    return value


async def main(project_id: int, name: str, description: str | None) -> None:
    """Create one Bug in ``project_id`` and print its new id."""
    fields: dict[str, object] = {"Name": name, "Project": {"Id": project_id}}
    if description is not None:
        fields["Description"] = description

    async with TargetProcessClient(
        domain=_env("TP_DOMAIN"),
        token=_env("TP_TOKEN"),
        mode=ClientMode.READWRITE,
    ) as client:
        bug = await client.bugs.create(**fields)
        print(f"created Bug {bug.id}: {bug.name} (project {project_id})")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Bug (write; requires --project-id and --yes)."
    )
    parser.add_argument(
        "--project-id",
        type=int,
        required=True,
        help="target project id — use a sandbox project (man8 sandbox: 49938), never production",
    )
    parser.add_argument("--name", default="Example bug from targetprocess-py", help="bug name")
    parser.add_argument("--description", default=None, help="optional bug description")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm the write — required, since this creates data in --project-id",
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
        asyncio.run(main(args.project_id, args.name, args.description))
    except TargetProcessError as exc:
        sys.exit(f"TargetProcess error: {exc}")
