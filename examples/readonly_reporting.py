#!/usr/bin/env python
"""Report open user stories grouped by workflow state (read-only).

Demonstrates a READONLY client used for reporting: a ``where=`` filter,
``include=`` field selection, lazy pagination across many pages, and
client-side aggregation — with no writes.

Configuration comes from the environment:

- ``TP_DOMAIN`` — instance domain, e.g. ``example.tpondemand.com``
- ``TP_TOKEN``  — API token (sent as the ``access_token`` query parameter)

Run:

    export TP_DOMAIN=example.tpondemand.com
    export TP_TOKEN=your-api-token
    python examples/readonly_reporting.py --limit 500
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter

from targetprocess import ClientMode, TargetProcessClient, TargetProcessError


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"error: environment variable {name} is required")
    return value


async def main(limit: int, page_size: int) -> None:
    """Tally non-final user stories by their workflow-state name."""
    by_state: Counter[str] = Counter()
    async with TargetProcessClient(
        domain=_env("TP_DOMAIN"),
        token=_env("TP_TOKEN"),
        mode=ClientMode.READONLY,
    ) as client:
        async for story in client.user_stories.list(
            where="(EntityState.IsFinal eq 'false')",
            include=["EntityState"],
            limit=limit,
            page_size=page_size,
        ):
            state = (story.entity_state.name if story.entity_state else None) or "(no state)"
            by_state[state] += 1

    total = sum(by_state.values())
    print(f"Open user stories by state (sampled up to {limit}):\n")
    for state, count in by_state.most_common():
        print(f"  {count:>5}  {state}")
    print(f"\n  {total:>5}  total")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report open user stories by state (read-only).")
    parser.add_argument(
        "--limit", type=int, default=500, help="max stories to sample (default: 500)"
    )
    parser.add_argument(
        "--page-size", type=int, default=100, help="page size per request (default: 100)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        asyncio.run(main(args.limit, args.page_size))
    except TargetProcessError as exc:
        sys.exit(f"TargetProcess error: {exc}")
