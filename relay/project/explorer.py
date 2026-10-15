"""Project file explorer helpers."""

from __future__ import annotations

from relay.config import IMAGE_EXTENSIONS, TEXT_FILE_EXTENSIONS, _EXPLORER_SKIP_DIRS
from relay.project.root import resolve_project_child
from relay.state import AppState


def attachment_ext_from_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    dot = base.rfind(".")
    return base[dot:].lower() if dot >= 0 else ""


def attachable_project_file_kind(name: str) -> str | None:
    ext = attachment_ext_from_name(name)
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in TEXT_FILE_EXTENSIONS:
        return "file"
    return None


def explorer_entries(state: AppState, relative: str = "") -> list[dict[str, str]]:
    directory = resolve_project_child(state, relative)
    if not directory.is_dir():
        raise ValueError("Not a directory")
    rel_prefix = relative.replace("\\", "/").strip("/")
    entries: list[dict[str, str]] = []
    try:
        children = sorted(
            directory.iterdir(),
            key=lambda p: (0 if p.is_dir() else 1, p.name.lower()),
        )
    except OSError as exc:
        raise ValueError(str(exc)) from exc
    for child in children:
        name = child.name
        if child.is_dir() and name in _EXPLORER_SKIP_DIRS:
            continue
        child_rel = f"{rel_prefix}/{name}" if rel_prefix else name
        if child.is_dir():
            entries.append({"name": name, "path": child_rel, "kind": "dir"})
        elif child.is_file():
            entries.append({"name": name, "path": child_rel, "kind": "file"})
    return entries
