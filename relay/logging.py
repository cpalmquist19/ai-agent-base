"""Per-chat model output logs and file-manager helpers."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import TextIO

from relay.config import LOG_DIR
from relay.sessions.attachments import safe_session_dir_name


def ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def session_log_path(session_id: str) -> Path:
    safe = safe_session_dir_name(session_id)
    return ensure_log_dir() / f"chat_{safe}.log"


def open_session_log(session_id: str) -> TextIO:
    path = session_log_path(session_id)
    return path.open("a", encoding="utf-8", newline="\n")


def log_write(fh: TextIO | None, text: str) -> None:
    if fh is None:
        return
    try:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")
        fh.flush()
    except OSError as exc:
        print(f"Warning: could not write model log: {exc}")


def reveal_in_file_manager(path: Path) -> str:
    """Open the folder containing path; on Windows, select the file if it exists."""
    path = path.resolve()
    folder = path if path.is_dir() else path.parent
    folder.mkdir(parents=True, exist_ok=True)

    system = platform.system()
    try:
        if system == "Windows":
            if path.is_file():
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                os.startfile(folder)  # type: ignore[attr-defined]
        elif system == "Darwin":
            if path.is_file():
                subprocess.Popen(["open", "-R", str(path)])
            else:
                subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except OSError as exc:
        return f"Could not open file manager: {exc}\nPath: `{folder}`"
    return f"Opened `{folder}`"
