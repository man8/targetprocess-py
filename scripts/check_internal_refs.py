#!/usr/bin/env python3
"""Fail when a tracked file names a tracker issue or an agent session.

This repository is published; the tracker its references once pointed into is
not. Such a reference resolves for nobody outside that workspace, so to a
reader of the public repository it is dead text that also advertises internal
scheduling the code never depended on. Agent session URLs and their commit
trailers are the same problem in a different shape.

The rationale a reference carried belongs in the file as prose; the reference
itself belongs in the commit message, where ``git blame`` still reaches it.

Run with no arguments to check every tracked file, or pass paths to check only
those (how pre-commit invokes it, with the staged files).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# A tracker reference is an uppercase key, a dash and an issue number. The
# pattern is deliberately generic: enumerating the keys of a private workspace
# would publish the very list this guard exists to keep out of the repository,
# and would miss any key added later.
#
# Matching is case-sensitive on the evidence. Lower-cased, the same shape
# matches a locked dependency version (`pyyaml-6`, `mypy-2`), a GUID fragment
# and a regex character class, hundreds of times over; upper-cased it matched
# four distinct tokens across the whole tree.
#
# The digits lead the second character class for the same reason the session
# patterns below use character classes: spelt the other way round, the class's
# own source text reads as a reference and this module becomes its own first
# offender. The two orderings are otherwise identical, and the self-clean test
# is what keeps this one from being tidied back.
REFERENCE = re.compile(r"\b(?P<key>[A-Z][0-9A-Z]{1,5})-\d{1,6}\b")

# Public standards designations share the shape and are not references into
# anyone's tracker. Extend as more appear; each entry is a prefix, matched
# whole.
EXCLUDED_PREFIXES = ("CVE", "IEEE", "ISO", "PEP", "RFC", "SHA", "UTF")

# The session patterns are written with character classes so that this module
# does not match its own source: `[.]` and `[-]` match exactly one literal
# character, leaving the pattern's meaning unchanged.
PATTERNS = (
    REFERENCE,
    re.compile(r"claude[.]ai/code"),
    re.compile(r"Claude[-]Session"),
)


# Recorded names in these files spell a tracker reference. Renaming them means
# re-recording the cassettes under the fixed-point guard, which needs a
# read-write token window against a live instance, so they are permitted until
# that window comes.
#
# An entry is a path and nothing more: no reference, and no part of one, is
# written down here. The cost is that an entry exempts a whole file's
# references rather than one of them; what limits it is that an entry lapses
# as soon as the file stops carrying any reference at all, which the
# accompanying test asserts, and that it exempts references only - a session
# URL or trailer is refused in these files exactly as anywhere else.
ALLOWED_PATHS = (
    "tests/integration/test_live_readwrite.py",
    "tests/integration/test_live_readwrite_surfaces.py",
    "tests/integration/cassettes/test_live_readwrite/"
    "test_bulk_create_and_update_tasks_under_a_story.yaml",
    "tests/integration/cassettes/test_live_readwrite/"
    "test_request_create_update_delete_round_trip.yaml",
    "tests/integration/cassettes/test_live_readwrite/"
    "test_user_story_create_update_delete_round_trip.yaml",
    "tests/integration/cassettes/test_live_readwrite_surfaces/"
    "test_assignment_create_and_delete.yaml",
    "tests/integration/cassettes/test_live_readwrite_surfaces/"
    "test_attachment_upload_list_download_and_delete.yaml",
    "tests/integration/cassettes/test_live_readwrite_surfaces/"
    "test_comment_create_update_delete_round_trip.yaml",
    "tests/integration/cassettes/test_live_readwrite_surfaces/test_relation_create_and_delete.yaml",
    "tests/integration/cassettes/test_live_readwrite_surfaces/"
    "test_role_effort_create_update_delete_round_trip.yaml",
    "tests/integration/cassettes/test_live_readwrite_surfaces/"
    "test_team_assignment_create_and_delete.yaml",
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


def _allowlist_key(path: Path) -> str:
    """Return the repository-relative form of the path, as the allowlist spells it.

    Callers hand this script whatever git or pre-commit gave them, which is
    repository-relative; a caller passing an absolute path by hand would
    otherwise miss the allowlist and be told a permitted reference is a
    violation.
    """
    try:
        return path.resolve().relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def violations(paths: list[Path], allowed: tuple[str, ...] | None = None) -> list[str]:
    """Return one message per reference or session marker that is not permitted here."""
    permitted = ALLOWED_PATHS if allowed is None else allowed
    messages = []

    for path in sorted(paths):
        if not path.is_file():
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # A binary file carries no prose to leak. Any other read failure is
            # left to raise: a gate that cannot read a file has not cleared it.
            continue

        references_permitted = _allowlist_key(path) in permitted
        for number, line in enumerate(text.splitlines(), start=1):
            for pattern in PATTERNS:
                for match in pattern.finditer(line):
                    key = match.groupdict().get("key")
                    if key is not None and (key in EXCLUDED_PREFIXES or references_permitted):
                        continue
                    messages.append(f"{path}:{number}: {match.group(0)}: {line.strip()}")

    return messages


def main(argv: list[str] | None = None) -> int:
    """Check the given paths (or all tracked files) and report internal references."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="files to check (default: all tracked)")
    args = parser.parse_args(argv)

    messages = violations(args.paths or _tracked_files())
    if not messages:
        return 0

    print("Internal references in tracked files:", file=sys.stderr)
    for message in messages:
        print(f"  {message}", file=sys.stderr)
    print(
        "\nThis repository is public and the tracker is not. Keep the rationale "
        "in the file as prose and put the reference in the commit message, where "
        "git blame still reaches it. A public standards designation caught by the "
        "shape belongs in EXCLUDED_PREFIXES; a reference that genuinely has to "
        "stay needs its path in ALLOWED_PATHS, with the reason.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
