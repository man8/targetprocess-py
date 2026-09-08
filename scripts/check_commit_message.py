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
import subprocess
import sys
from pathlib import Path

from check_internal_refs import EXCLUDED_PREFIXES, REFERENCE

DEFAULT_COMMENT_PREFIX = "#"

# git discards the scissors line and everything after it when it reads the
# message back from the editor (`git commit --verbose` places the diff below
# it). The line starts with the comment prefix, whatever that is configured as.
SCISSORS_RULE = " ------------------------ >8 ------------------------"


def comment_prefix() -> str:
    """Return git's effective comment prefix for this repository, `#` by default.

    `core.commentString` (any string) supersedes `core.commentChar` (one
    character); `auto` makes git pick a character per message, which cannot be
    known here, so it falls back to the default like an unset value does.
    """
    for key in ("core.commentString", "core.commentChar"):
        try:
            result = subprocess.run(
                ["git", "config", "--get", key],
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError:
            return DEFAULT_COMMENT_PREFIX
        value = result.stdout.strip()
        if value and value != "auto":
            return value
    return DEFAULT_COMMENT_PREFIX


def message_lines(text: str, prefix: str = DEFAULT_COMMENT_PREFIX) -> list[tuple[int, str]]:
    """Return the lines git would keep, each with its physical line number.

    Nothing below the scissors line is kept, and no comment line is; the
    numbers are those of the original message, so a report points at the line
    the author sees.
    """
    scissors = prefix + SCISSORS_RULE
    kept: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line == scissors:
            break
        if line.startswith(prefix):
            continue
        kept.append((number, line))
    return kept


def violations(text: str, prefix: str = DEFAULT_COMMENT_PREFIX) -> list[str]:
    """Return one message per tracker reference in the commit message."""
    messages = []
    for number, line in message_lines(text, prefix):
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

    messages = violations(text, comment_prefix())
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
