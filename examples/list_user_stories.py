#!/usr/bin/env python
"""List user stories from a TargetProcess instance (read-only).

Demonstrates a READONLY client, a ``where=`` filter, ``include=`` field
selection, and iterating the async ``list()`` generator.

Configuration comes from the environment:

- ``TP_DOMAIN`` — instance domain, e.g. ``example.tpondemand.com``
- ``TP_TOKEN``  — API token (sent as the ``access_token`` query parameter)

Run:

    export TP_DOMAIN=example.tpondemand.com
    export TP_TOKEN=your-api-token
    python examples/list_user_stories.py --limit 10
    python examples/list_user_stories.py --where "(EntityState.Name eq 'Open')"
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


async def main(where: str | None, limit: int) -> None:
    """List user stories and print ``id: name [state]`` for each."""
    async with TargetProcessClient(
        domain=_env("TP_DOMAIN"),
        token=_env("TP_TOKEN"),
        mode=ClientMode.READONLY,
    ) as client:
        count = 0
        async for story in client.user_stories.list(
            where=where,
            include=["EntityState"],
            limit=limit,
        ):
            state = story.entity_state.name if story.entity_state else "—"
            print(f"{story.id}: {story.name} [{state}]")
            count += 1
        print(f"\n{count} user stor{'y' if count == 1 else 'ies'} listed.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List user stories (read-only).")
    parser.add_argument("--where", default=None, help="TargetProcess where= filter expression")
    parser.add_argument("--limit", type=int, default=10, help="max stories to list (default: 10)")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        asyncio.run(main(args.where, args.limit))
    except TargetProcessError as exc:
        sys.exit(f"TargetProcess error: {exc}")
