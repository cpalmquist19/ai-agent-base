"""Tools the agent can call: path confinement, editing rules, calculator safety."""

from __future__ import annotations

import pytest

from lm_studio_chat.tools.builtin import tool_calculate
from lm_studio_chat.tools.filesystem import (
    resolve_tool_path,
    tool_list_dir,
    tool_read_file,
    tool_search_file,
    tool_str_replace,
    tool_write_file,
)


@pytest.fixture
def state(make_state):
    return make_state([])[0]


def test_paths_inside_the_project_resolve(state, tmp_path):
    assert resolve_tool_path(state, "sub/file.txt") == (tmp_path / "sub" / "file.txt").resolve()


@pytest.mark.parametrize("bad", ["../escape.txt", "sub/../../escape.txt"])
def test_relative_escapes_are_rejected(state, bad):
    with pytest.raises(ValueError, match="outside"):
        resolve_tool_path(state, bad)


def test_absolute_paths_outside_the_project_are_rejected(state, tmp_path):
    outside = tmp_path.parent / "outside.txt"
    with pytest.raises(ValueError, match="outside"):
        resolve_tool_path(state, str(outside))


def test_tools_report_confinement_as_an_error_string(state, tmp_path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    assert tool_read_file(state, str(outside)).startswith("Error")
    assert tool_write_file(state, str(tmp_path.parent / "new.txt"), "x").startswith("Error")
    assert tool_list_dir(state, str(tmp_path.parent)).startswith("Error")
    assert not (tmp_path.parent / "new.txt").exists()


def test_unrestricted_flag_disables_confinement(state, tmp_path, monkeypatch):
    # Documents the escape hatch: it exists, and it is the only way out of the sandbox.
    outside = tmp_path.parent / "ok.txt"
    outside.write_text("fine", encoding="utf-8")
    monkeypatch.setenv("LM_STUDIO_ALLOW_UNRESTRICTED_PATHS", "1")
    assert "fine" in tool_read_file(state, str(outside))


def test_write_file_creates_parent_folders(state, tmp_path):
    assert tool_write_file(state, "a/b/c.txt", "hi").startswith("Wrote")
    assert (tmp_path / "a" / "b" / "c.txt").read_text(encoding="utf-8") == "hi"


def test_read_file_returns_numbered_slice(state, tmp_path):
    (tmp_path / "f.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    out = tool_read_file(state, "f.txt", start_line=2, end_line=3)
    assert "two" in out and "three" in out and "one" not in out


def test_search_file_finds_matches_and_reports_misses(state, tmp_path):
    (tmp_path / "f.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    assert "match at line 2" in tool_search_file(state, "f.txt", "beta")
    assert tool_search_file(state, "f.txt", "zzz").startswith("No matches")


def test_search_file_rejects_directories_and_bad_regex(state, tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    assert tool_search_file(state, "d", "x").startswith("Error")
    assert tool_search_file(state, "f.txt", "(").startswith("Error: invalid regex")


def test_str_replace_edits_exactly_one_occurrence(state, tmp_path):
    (tmp_path / "f.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    assert tool_str_replace(state, "f.py", "b = 2", "b = 3").startswith("Replaced")
    assert (tmp_path / "f.py").read_text(encoding="utf-8") == "a = 1\nb = 3\n"


def test_str_replace_refuses_missing_and_ambiguous_matches(state, tmp_path):
    (tmp_path / "f.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    assert "not found" in tool_str_replace(state, "f.py", "y = 1", "z")
    assert "matched 2 times" in tool_str_replace(state, "f.py", "x = 1", "x = 2")
    assert (tmp_path / "f.py").read_text(encoding="utf-8") == "x = 1\nx = 1\n"  # untouched


def test_calculate_does_arithmetic():
    assert tool_calculate("2480 * 0.175") == "434.0"
    assert tool_calculate("sqrt(16) + abs(-2)") == "6.0"


def test_calculate_reports_bad_input_as_an_error():
    assert tool_calculate("2 +").startswith("Error")
    assert tool_calculate("1 / 0").startswith("Error")


@pytest.mark.parametrize(
    "payload",
    [
        "__import__('os').getcwd()",
        "().__class__",
        "(1).__class__.__bases__",
        "[c for c in ().__class__.__base__.__subclasses__()]",
        "open('x')",
        "exec('x = 1')",
    ],
)
def test_calculate_cannot_be_used_to_run_code(payload):
    """The model controls this string, and so can any web page it reads (prompt injection)."""
    assert tool_calculate(payload).startswith("Error")
