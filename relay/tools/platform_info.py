"""What operating system and shell run_command really uses, so the model is told the truth.

Models cannot see the machine they are controlling. If the tool description says "PowerShell"
but the code starts cmd.exe, a model that follows the description writes commands that fail.
"""

from __future__ import annotations

import os


def shell_syntax(is_windows: bool | None = None) -> str:
    """Short description of the shell syntax run_command accepts on this machine."""
    windows = (os.name == "nt") if is_windows is None else is_windows
    if windows:
        return (
            "Windows cmd.exe syntax, NOT PowerShell; for PowerShell run "
            "powershell -NoProfile -Command \"...\""
        )
    return "POSIX /bin/sh syntax (Linux or macOS)"


def environment_note(is_windows: bool | None = None) -> str:
    """One line for the system prompt."""
    windows = (os.name == "nt") if is_windows is None else is_windows
    system = "Windows" if windows else "Linux/macOS"
    return f"Operating system: {system}. run_command uses {shell_syntax(windows)}."
