"""Shell command execution and cwd persistence."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from lm_studio_chat.config import COMMAND_OUTPUT_LIMIT, allow_unrestricted_paths
from lm_studio_chat.state import AppState


def terminate_process_tree(proc: subprocess.Popen) -> None:
    """Best-effort kill of a shell command and its children."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=5,
                check=False,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    except (OSError, subprocess.TimeoutExpired):
        pass


def kill_active_command(state: AppState) -> None:
    with state.active_command_lock:
        proc = state.active_command_proc
    if proc is not None:
        terminate_process_tree(proc)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        try:
            Path(str(path.resolve()).lower()).relative_to(
                Path(str(root.resolve()).lower())
            )
            return True
        except ValueError:
            return False


def resolve_cd_target(state: AppState, target: str) -> Path:
    target = target.strip().strip('"').strip("'")
    if not target or target == "~":
        if not allow_unrestricted_paths():
            if state.project_root is not None:
                return state.project_root.resolve()
        return Path.home().resolve()
    expanded = Path(os.path.expandvars(target)).expanduser()
    if not expanded.is_absolute():
        expanded = state.shell_cwd / expanded
    resolved = expanded.resolve()

    if not allow_unrestricted_paths():
        sandbox_root = (state.project_root or state.shell_cwd).resolve()
        if not _is_relative_to(resolved, sandbox_root):
            target_label = "the open project" if state.project_root is not None else "the working directory"
            raise ValueError(f"target directory is outside {target_label}: {target} (resolved: {resolved})")

    return resolved


def tool_run_command(state: AppState, command: str, timeout_seconds: int = 60) -> str:
    """Run a shell command. Plain `cd` updates the persistent working directory."""
    command = command.strip()
    if not command:
        return "Error: empty command."

    cd_match = re.match(r"^cd(?:\s+(.*))?$", command, re.IGNORECASE | re.DOTALL)
    if cd_match and "&&" not in command and "|" not in command and ";" not in command:
        target = (cd_match.group(1) or "").strip()
        try:
            new_cwd = resolve_cd_target(state, target)
        except (OSError, ValueError) as exc:
            return f"Error resolving path: {exc}"
        if not new_cwd.is_dir():
            return f"Error: '{new_cwd}' is not a directory.\nCWD: {state.shell_cwd}"
        state.shell_cwd = new_cwd
        return f"Changed directory to {state.shell_cwd}"

    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(state.shell_cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return f"Error launching command: {exc}\nCWD: {state.shell_cwd}"

    with state.active_command_lock:
        state.active_command_proc = proc
    deadline = time.monotonic() + max(1, int(timeout_seconds))
    cancelled = False
    timed_out = False
    try:
        while proc.poll() is None:
            if state.cancel.is_set():
                cancelled = True
                terminate_process_tree(proc)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                terminate_process_tree(proc)
                break
            time.sleep(0.1)
        stdout, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        terminate_process_tree(proc)
        stdout, stderr = proc.communicate()
        timed_out = True
    finally:
        with state.active_command_lock:
            if state.active_command_proc is proc:
                state.active_command_proc = None

    if cancelled:
        return f"Error: command cancelled by user.\nCWD: {state.shell_cwd}"
    if timed_out:
        return (
            f"Error: command timed out after {timeout_seconds}s.\n"
            f"CWD: {state.shell_cwd}"
        )

    chunks = [f"CWD: {state.shell_cwd}", f"exit_code: {proc.returncode}"]
    stdout = (stdout or "").rstrip()
    stderr = (stderr or "").rstrip()
    if stdout:
        chunks.append("--- stdout ---\n" + stdout)
    if stderr:
        chunks.append("--- stderr ---\n" + stderr)
    if not stdout and not stderr:
        chunks.append("(no output)")

    text = "\n".join(chunks)
    if len(text) > COMMAND_OUTPUT_LIMIT:
        text = text[:COMMAND_OUTPUT_LIMIT] + f"\n... (truncated at {COMMAND_OUTPUT_LIMIT} chars)"
    return text
