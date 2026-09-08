#!/usr/bin/env python3
"""Fail when a tracked file grows past the size or line-count ceiling.

Oversized files are the shape of code that has stopped being reviewable: a
2000-line module hides its own structure, and a committed binary bloats every
clone forever. This flags both, over the files git actually tracks.

Run with no arguments to check every tracked file, or pass paths to check only
those (how pre-commit invokes it, with the staged files).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

MAX_LINES = 1000
MAX_KIB = 256

# Generated artefacts whose size is a product of what they record, not of a
# design decision a reviewer could act on: the uv lockfile enumerates the whole
# resolved graph, and a VCR cassette is as long as the API traffic it replays.
EXCLUDED = (
    "uv.lock",
    "tests/integration/cassettes/*",
)


def _tracked_files() -> list[Path]:
    """Return every file tracked by git, relative to the repository root."""
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return [Path(name) for name in out.split("\0") if name]


def _is_excluded(path: Path) -> bool:
    """Report whether the path is a generated artefact exempt from the ceilings."""
    posix = path.as_posix()
    return any(fnmatch(posix, pattern) for pattern in EXCLUDED)


def _count_lines(path: Path) -> int | None:
    """Return the file's line count, or None if it is not decodable as text."""
    try:
        with path.open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except (UnicodeDecodeError, ValueError):
        return None


def _violations(paths: list[Path], max_lines: int, max_kib: int) -> list[str]:
    """Return one message per file that breaches a ceiling."""
    messages = []
    for path in sorted(paths):
        if _is_excluded(path) or not path.is_file():
            continue

        kib = path.stat().st_size / 1024
        if kib > max_kib:
            messages.append(f"{path}: {kib:.0f} KiB exceeds the {max_kib} KiB ceiling")

        lines = _count_lines(path)
        if lines is not None and lines > max_lines:
            messages.append(f"{path}: {lines} lines exceeds the {max_lines} line ceiling")

    return messages


def main(argv: list[str] | None = None) -> int:
    """Check the given paths (or all tracked files) and report any breaches."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="files to check (default: all tracked)")
    parser.add_argument("--max-lines", type=int, default=MAX_LINES)
    parser.add_argument("--max-kib", type=int, default=MAX_KIB)
    args = parser.parse_args(argv)

    messages = _violations(args.paths or _tracked_files(), args.max_lines, args.max_kib)
    if not messages:
        return 0

    print("Files exceeding the size ceilings:", file=sys.stderr)
    for message in messages:
        print(f"  {message}", file=sys.stderr)
    print(
        "\nSplit the file along a real seam, or add it to EXCLUDED in "
        "scripts/check_large_files.py if it is a generated artefact.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
