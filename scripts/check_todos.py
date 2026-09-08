#!/usr/bin/env python3
"""Fail when a debt marker in code carries no issue reference.

An unattributed marker is debt nobody owns: it never surfaces on a board, never
gets scheduled, and outlives the person who wrote it. Requiring the issue
reference inline — ``TODO(#123): explain what is owed`` — makes every marker
traceable to a tracked, prioritised item.

Run with no arguments to check every tracked file, or pass paths to check only
those (how pre-commit invokes it, with the staged files).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

MARKERS = ("TODO", "FIXME", "HACK", "XXX")

# What introduces the issue number inside the parentheses. ``#`` is a GitHub
# issue reference, the form this project uses; another tracker's layout is
# reached by passing its own introducer, separator included, to ``--prefix``.
DEFAULT_PREFIX = "#"

# Prose is not code: a marker in Markdown is documentation about markers (this
# repo's own docs describe the convention), not debt hiding in a code path.
SCANNED_SUFFIXES = frozenset(
    {".py", ".pyi", ".toml", ".yaml", ".yml", ".sh", ".cfg", ".ini", ".json"}
)

# This scanner names the markers it looks for, so scanning itself would match
# every one of them.
SELF = Path(__file__).resolve()


def _tracked_files() -> list[Path]:
    """Return every file tracked by git, relative to the repository root."""
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return [Path(name) for name in out.split("\0") if name]


def _marker_pattern(prefix: str) -> re.Pattern[str]:
    """Return a pattern matching a debt marker that is not followed by an issue reference."""
    markers = "|".join(MARKERS)
    return re.compile(rf"\b(?:{markers})\b(?!\({re.escape(prefix)}\d+\))")


def _violations(paths: list[Path], prefix: str) -> list[str]:
    """Return one message per unattributed marker found."""
    pattern = _marker_pattern(prefix)
    messages = []

    for path in sorted(paths):
        if path.suffix not in SCANNED_SUFFIXES or not path.is_file():
            continue
        if path.resolve() == SELF:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                messages.append(f"{path}:{number}: {line.strip()}")

    return messages


def main(argv: list[str] | None = None) -> int:
    """Check the given paths (or all tracked files) and report unattributed markers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="files to check (default: all tracked)")
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help="text introducing the issue number inside the parentheses",
    )
    args = parser.parse_args(argv)

    messages = _violations(args.paths or _tracked_files(), args.prefix)
    if not messages:
        return 0

    markers = ", ".join(MARKERS)
    print("Debt markers without an issue reference:", file=sys.stderr)
    for message in messages:
        print(f"  {message}", file=sys.stderr)
    print(
        f"\nEvery {markers} marker must name the issue that tracks it, "
        f"e.g. {MARKERS[0]}({args.prefix}123): explain what is owed.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
