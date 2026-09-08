"""Tests for the commit-message guard.

As in the internal-reference tests, every planted reference is composed at
runtime: the tree guard scans this module like any other tracked file.
"""

import importlib
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / "scripts"

_KEY = "ABCD"
_HOST = "claude.ai"
_SESSION = "Session"


def _load_guard() -> ModuleType:
    """Import the guard with scripts/ on the path, so its sibling import resolves."""
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    return importlib.import_module("check_commit_message")


guard = _load_guard()


def _ref(number: str, key: str = _KEY) -> str:
    return f"{key}-{number}"


def _trailers() -> str:
    return (
        "Co-Authored-By: Example Agent <agent@example.com>\n"
        f"Claude-{_SESSION}: https://{_HOST}/code/session_0123456789abcdef\n"
    )


def test_a_conventional_message_passes() -> None:
    text = "feat: add a thing\n\nBecause it was missing.\n\nFixes #123\n"

    assert guard.violations(text) == []


def test_the_attribution_trailers_pass() -> None:
    assert guard.violations("fix: a thing\n\n" + _trailers()) == []


def test_a_reference_in_the_subject_is_flagged() -> None:
    messages = guard.violations(f"{_ref('1234')}: add a thing\n")

    assert len(messages) == 1
    assert _ref("1234") in messages[0]
    assert "line 1" in messages[0]


def test_a_reference_in_the_body_is_flagged() -> None:
    messages = guard.violations(f"feat: add a thing\n\nSee {_ref('99')}.\n")

    assert len(messages) == 1
    assert "line 3" in messages[0]


@pytest.mark.parametrize("prefix", guard.EXCLUDED_PREFIXES)
def test_public_standards_designations_pass(prefix: str) -> None:
    assert guard.violations(f"fix: handle {prefix}-2024 correctly\n") == []


def test_comment_lines_and_the_scissors_block_are_ignored() -> None:
    text = (
        "feat: add a thing\n"
        f"# {_ref('1')} in a comment line\n"
        f"{guard.SCISSORS}\n"
        f"{_ref('2')} below the scissors\n"
    )

    assert guard.violations(text) == []


@pytest.mark.parametrize(
    ("message", "expected"),
    [("ci: check the title\n", 0), ("{ref}: check the title\n", 1)],
)
def test_the_cli_reads_stdin(message: str, expected: int) -> None:
    """The stdin form is how CI checks a pull request title."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPTS / "check_commit_message.py"), "--stdin"],
        input=message.format(ref=_ref("5")),
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == expected
