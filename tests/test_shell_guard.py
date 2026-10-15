"""run_command: the best-effort outside-the-project guard and the platform description."""

from __future__ import annotations

import os

import pytest

from relay.chat.prompts import build_system_prompt
from relay.tools.platform_info import environment_note, shell_syntax
from relay.tools.schemas import TOOL_SCHEMAS
from relay.tools.shell import command_path_violation, tool_run_command


@pytest.fixture
def state(make_state):
    return make_state([])[0]


def _outside(tmp_path):
    secret = tmp_path.parent / "secret_outside.txt"
    secret.write_text("CANARY-123", encoding="utf-8")
    return secret


def test_command_naming_a_file_outside_the_project_is_blocked(state, tmp_path):
    secret = _outside(tmp_path)
    for command in (f'type "{secret}"', f"cat {secret}", f'python -c "print(open(r\'{secret}\').read())"'):
        assert command_path_violation(state, command) is not None, command
        result = tool_run_command(state, command)
        assert result.startswith("Error: command refers to a path outside")
        assert "CANARY-123" not in result


def test_parent_directory_and_home_escapes_are_blocked(state, tmp_path, monkeypatch):
    for var in ("HOME", "USERPROFILE"):  # a home directory that is not inside the project
        monkeypatch.setenv(var, str(tmp_path.parent))
    commands = ["type ..\\secret.txt", "cat ../secret.txt", "dir ..", "cat ~/.ssh/id_rsa", "cat $HOME/x"]
    if os.name == "nt":
        commands.append("type %USERPROFILE%\\notes.txt")
    for command in commands:
        assert command_path_violation(state, command) is not None, command


def test_unix_system_paths_outside_the_project_are_blocked_but_program_dirs_are_not(state):
    if os.name == "nt":
        pytest.skip("POSIX absolute-path rules do not apply on Windows")
    assert command_path_violation(state, "cat /etc/passwd") is not None
    assert command_path_violation(state, "/usr/bin/env python --version") is None


def test_ordinary_project_commands_are_allowed(state, tmp_path):
    inside = tmp_path / "notes.txt"
    inside.write_text("hi", encoding="utf-8")
    for command in ("python --version", "echo hello > out.txt", "git status", f'echo "{inside}"', "dir sub\\..", "ls ./sub/../"):
        assert command_path_violation(state, command) is None, command
    assert "hello" in tool_run_command(state, "echo hello")


def test_urls_and_flags_are_not_mistaken_for_paths(state):
    commands = ["curl https://example.com/a/b", "git log --oneline -n 3"]
    if os.name == "nt":
        commands.append("dir /s /b")  # cmd.exe switches, not paths
    for command in commands:
        assert command_path_violation(state, command) is None, command


def test_unrestricted_flag_turns_the_guard_off(state, tmp_path, monkeypatch):
    secret = _outside(tmp_path)
    monkeypatch.setenv("LM_STUDIO_ALLOW_UNRESTRICTED_PATHS", "1")
    cmd = f'type "{secret}"' if os.name == "nt" else f"cat {secret}"
    assert "CANARY-123" in tool_run_command(state, cmd)


# ---- telling the model the truth about the shell -------------------------------


def test_shell_description_matches_the_platform():
    windows = shell_syntax(is_windows=True)
    assert "cmd.exe" in windows and "NOT PowerShell" in windows
    assert "/bin/sh" in shell_syntax(is_windows=False)
    assert "Windows" in environment_note(is_windows=True) and "Linux/macOS" in environment_note(is_windows=False)


def test_the_run_command_tool_and_system_prompt_state_the_real_shell(state):
    run_command = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "run_command")
    assert shell_syntax() in run_command["function"]["description"]
    assert "PowerShell syntax" not in run_command["function"]["description"].replace("NOT PowerShell", "")
    assert environment_note() in build_system_prompt(state)
