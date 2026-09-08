"""Tests for the internal-reference guard.

Every reference planted here is invented and composed at runtime. The guard
scans its own test module like any other tracked file, so a literal reference
in this file would fail the very check these tests exercise — and a real
tracker key would be the thing the guard exists to keep out.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "check_internal_refs.py"

# The pieces the planted references are built from, each harmless alone.
_KEY = "ABCD"
_HOST = "claude.ai"
_CODE = "code"
_SESSION = "Session"


def _load_guard() -> ModuleType:
    """Import the guard from its path: scripts/ is a directory, not a package."""
    spec = importlib.util.spec_from_file_location("check_internal_refs", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


def _ref(number: str, key: str = _KEY) -> str:
    return f"{key}-{number}"


def _session_url() -> str:
    return f"https://{_HOST}/{_CODE}/session_0123456789abcdef"


def _session_trailer() -> str:
    return f"Claude-{_SESSION}: {_session_url()}"


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_a_tracker_reference_is_flagged(tmp_path: Path) -> None:
    path = _write(tmp_path, "note.py", f"# see {_ref('1234')} for the reason\n")

    messages = guard.violations([path])

    assert len(messages) == 1
    assert _ref("1234") in messages[0]
    assert "note.py:1" in messages[0]


@pytest.mark.parametrize("key", ["AB", "ABCDEF", "A1", "X9Y8Z7"])
def test_any_key_of_the_right_shape_is_flagged(tmp_path: Path, key: str) -> None:
    """The pattern is generic, so an unfamiliar key is caught without being enumerated."""
    path = _write(tmp_path, "note.py", f"# tracked as {_ref('7', key)}\n")

    assert guard.violations([path]) != []


@pytest.mark.parametrize("token", ["A-1", "ABCDEFG-1", "ABCD-1234567", "abcd-1234"])
def test_shapes_outside_the_reference_form_pass(tmp_path: Path, token: str) -> None:
    """A one-character key, an over-long key or number, and lower case are all excluded.

    Lower case is the deliberate one: matching it would also match every locked
    dependency version and every GUID fragment in the tree.
    """
    path = _write(tmp_path, "note.py", f"value = '{token}'\n")

    assert guard.violations([path]) == []


@pytest.mark.parametrize("prefix", guard.EXCLUDED_PREFIXES)
def test_a_public_standard_is_not_a_reference(tmp_path: Path, prefix: str) -> None:
    path = _write(tmp_path, "note.py", f"# encoded per {prefix}-8601\n")

    assert guard.violations([path]) == []


def test_an_excluded_prefix_does_not_excuse_a_neighbouring_reference(tmp_path: Path) -> None:
    body = f"# {guard.EXCLUDED_PREFIXES[0]}-8601 dates, tracked as {_ref('1234')}\n"
    path = _write(tmp_path, "note.py", body)

    messages = guard.violations([path])

    assert len(messages) == 1
    assert _ref("1234") in messages[0]


def test_a_key_without_a_number_is_not_a_reference(tmp_path: Path) -> None:
    path = _write(tmp_path, "note.py", f"# the {_KEY} team owns this module\n")

    assert guard.violations([path]) == []


def test_a_session_url_is_flagged(tmp_path: Path) -> None:
    path = _write(tmp_path, "note.md", f"Written in {_session_url()} on Sunday.\n")

    messages = guard.violations([path])

    assert len(messages) == 1
    assert f"{_HOST}/{_CODE}" in messages[0]


def test_a_session_trailer_is_flagged(tmp_path: Path) -> None:
    path = _write(tmp_path, "note.txt", f"{_session_trailer()}\n")

    messages = guard.violations([path])

    assert any(f"Claude-{_SESSION}" in message for message in messages)


def test_a_clean_file_passes(tmp_path: Path) -> None:
    path = _write(tmp_path, "clean.py", "# nothing internal here\nvalue = 1\n")

    assert guard.violations([path]) == []


def test_an_allowed_path_may_carry_references(tmp_path: Path) -> None:
    body = f"name: {_ref('1234')} recording\n# and see {_ref('5678')}\n"
    path = _write(tmp_path, "recorded.yaml", body)

    assert guard.violations([path], (path.as_posix(),)) == []


def test_an_allowed_path_is_still_refused_a_session_marker(tmp_path: Path) -> None:
    """A path entry exempts references only; a session URL is refused everywhere."""
    path = _write(tmp_path, "recorded.yaml", f"name: {_ref('1234')}\nby: {_session_url()}\n")

    messages = guard.violations([path], (path.as_posix(),))

    assert len(messages) == 1
    assert f"{_HOST}/{_CODE}" in messages[0]


def test_an_undecodable_file_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(b"\xff\xfe" + _ref("1234").encode("utf-16-le"))

    assert guard.violations([path]) == []


def test_the_guard_and_its_own_tests_carry_no_references() -> None:
    assert guard.violations([_SCRIPT, Path(__file__).resolve()]) == []


@pytest.mark.parametrize("allowed_path", guard.ALLOWED_PATHS, ids=lambda entry: entry)
def test_every_allowed_path_still_needs_its_entry(allowed_path: str) -> None:
    """A stale entry is a hole: it must go when the file stops carrying a reference.

    Checked by shape rather than by the reference itself, so nothing about the
    reference is written down here either. Excluded prefixes do not count - a
    cassette whose only match is a charset header has stopped earning its entry.
    """
    path = _REPO_ROOT / allowed_path
    assert path.is_file(), f"{path} no longer exists; drop the entry"

    matches = [
        match
        for match in guard.REFERENCE.finditer(path.read_text(encoding="utf-8"))
        if match.group("key") not in guard.EXCLUDED_PREFIXES
    ]
    assert matches, f"{path} no longer carries a reference; drop the entry"


def test_main_succeeds_on_a_clean_path(tmp_path: Path) -> None:
    path = _write(tmp_path, "clean.py", "value = 1\n")

    assert guard.main([str(path)]) == 0


def test_main_fails_and_names_the_reference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "dirty.py", f"# {_ref('1234')}\n")

    assert guard.main([str(path)]) == 1
    assert _ref("1234") in capsys.readouterr().err
