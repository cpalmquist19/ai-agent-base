"""Project root persistence and folder picker."""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from relay.config import PROJECT_FILE
from relay.state import AppState


def load_project_root() -> Path | None:
    if not PROJECT_FILE.is_file():
        return None
    try:
        data = json.loads(PROJECT_FILE.read_text(encoding="utf-8"))
        raw = (data.get("root") or "").strip()
        if not raw:
            return None
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            return path
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return None


def save_project_root(path: Path | None) -> None:
    if path is None:
        if PROJECT_FILE.is_file():
            PROJECT_FILE.unlink(missing_ok=True)
        return
    PROJECT_FILE.write_text(
        json.dumps({"root": str(path.resolve())}, indent=2),
        encoding="utf-8",
    )


def set_project_root(state: AppState, path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"'{resolved}' is not a directory")
    state.project_root = resolved
    state.shell_cwd = resolved
    save_project_root(resolved)
    return resolved


def clear_project_root(state: AppState) -> None:
    state.project_root = None
    save_project_root(None)


def resolve_project_child(state: AppState, relative: str = "") -> Path:
    if state.project_root is None:
        raise ValueError("No project is open")
    rel = relative.replace("\\", "/").strip("/")
    target = (state.project_root / rel).resolve() if rel else state.project_root.resolve()
    root = state.project_root.resolve()
    if target != root and root not in target.parents:
        raise ValueError("Path is outside the project")
    return target


def _pick_folder_dialog_windows(initial_dir: Path | None = None) -> str | None:
    initial = ""
    if initial_dir is not None and initial_dir.is_dir():
        initial = str(initial_dir).replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$d.Description = 'Select project folder'; "
        "$d.ShowNewFolderButton = $false; "
    )
    if initial:
        ps += f"$d.SelectedPath = '{initial}'; "
    ps += (
        "$r = $d.ShowDialog(); "
        "if ($r -eq [System.Windows.Forms.DialogResult]::OK) { $d.SelectedPath }"
    )
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    selected = (completed.stdout or "").strip()
    if not selected or completed.returncode != 0:
        return None
    try:
        return str(Path(selected).expanduser().resolve())
    except OSError:
        return None


def pick_folder_dialog(initial_dir: Path | None = None) -> str | None:
    """Native folder picker. Returns absolute path or None if cancelled."""
    if platform.system() == "Windows":
        selected = _pick_folder_dialog_windows(initial_dir)
        if selected:
            return selected

    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    kwargs: dict[str, Any] = {"mustexist": True}
    if initial_dir is not None and initial_dir.is_dir():
        kwargs["initialdir"] = str(initial_dir)
    selected = filedialog.askdirectory(**kwargs)
    root.destroy()
    if not selected:
        return None
    return str(Path(selected).expanduser().resolve())
