#!/usr/bin/env python3
"""Fail when a commit message names a tracker issue.

The tree is kept free of tracker references by ``check_internal_refs.py``;
this hook keeps them out of the history too, where a squash merge would
otherwise carry them onto ``main`` for good. The same shape is refused and
the same public standards designations are excused. An issue on this
repository is referenced as ``Fixes #123``, which resolves for every reader.

Attribution trailers - a co-author line, or the trailer naming the agent
session that produced a change - are allowed: they disclose how the change
was made, which this repository chooses to keep, and they carry no tracker
reference.

Reads the message from the file pre-commit hands a commit-msg hook, or from
stdin with ``--stdin`` (how CI checks a pull request title, which squash
merge turns into the commit on ``main``). Comment lines and everything below
git's scissors line are ignored, as git ignores them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from check_internal_refs import EXCLUDED_PREFIXES, REFERENCE

# git discards this line and everything after it when it reads the message
# back from the editor (`git commit --verbose` places the diff below it).
SCISSORS = "# ------------------------ >8 ------------------------"


def message_lines(text: str) -> list[str]:
    """Return the lines git would keep: nothing below the scissors, no comment lines."""
    kept: list[str] = []
    for line in text.splitlines():
        if line == SCISSORS:
            break
        if line.startswith("#"):
            continue
        kept.append(line)
    return kept


def violations(text: str) -> list[str]:
    """Return one message per tracker reference in the commit message."""
    messages = []
    for number, line in enumerate(message_lines(text), start=1):
        for match in REFERENCE.finditer(line):
            if match.group("key") in EXCLUDED_PREFIXES:
                continue
            messages.append(f"line {number}: {match.group(0)}: {line.strip()}")
    return messages


def main(argv: list[str] | None = None) -> int:
    """Check a commit message file, or stdin, and report tracker references."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, help="the commit message file")
    parser.add_argument("--stdin", action="store_true", help="read the message from stdin")
    args = parser.parse_args(argv)

    if args.stdin:
        text = sys.stdin.read()
    elif args.path is not None:
        text = args.path.read_text(encoding="utf-8")
    else:
        parser.error("give the commit message file, or --stdin")

    messages = violations(text)
    if not messages:
        return 0

    print("Tracker references in the commit message:", file=sys.stderr)
    for message in messages:
        print(f"  {message}", file=sys.stderr)
    print(
        "\nThis repository is public and the tracker is not. Reference an issue on "
        "this repository as `Fixes #123`, and keep tracker keys out of the history. "
        "A public standards designation caught by the shape belongs in "
        "EXCLUDED_PREFIXES in check_internal_refs.py.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
