"""Filesystem tools: read, search, list, write, str_replace."""

from __future__ import annotations

import os
import re
from pathlib import Path

from lm_studio_chat.state import AppState


def resolve_tool_path(state: AppState, path: str) -> Path:
    """Resolve a file/dir path for tool I/O against the persistent shell cwd."""
    raw = path.strip()
    if not raw:
        raise ValueError("empty path")
    expanded = Path(os.path.expandvars(raw)).expanduser()
    if not expanded.is_absolute():
        expanded = state.shell_cwd / expanded
    return expanded.resolve()


def tool_read_file(
    state: AppState,
    path: str,
    start_line: int = 1,
    end_line: int | None = None,
    max_chars: int = 30000,
) -> str:
    """Read a slice of a UTF-8 text file by 1-based line numbers."""
    try:
        p = resolve_tool_path(state, path)
    except ValueError as exc:
        return f"Error: {exc}"
    if not p.is_file():
        return f"Error: {path} is not a file (resolved: {p})."
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except OSError as exc:
        return f"Error reading {path}: {exc}"

    total = len(lines)
    if total == 0:
        return "(empty file)"

    start = max(1, int(start_line))
    end = int(end_line) if end_line is not None else total
    end = min(total, max(start, end))

    chunk_lines = lines[start - 1 : end]
    numbered = "".join(f"{i}|{line}" for i, line in enumerate(chunk_lines, start=start))
    header = f"File: {p.resolve()} | lines {start}-{end} of {total}\n"
    body = header + numbered
    note = (
        "\n(Note: leading 'LINE|' markers are for navigation only - "
        "omit them when copying into str_replace old_string.)"
    )
    if len(body) > max_chars:
        return body[:max_chars] + f"\n... (truncated at {max_chars} chars)" + note
    return body + note


def tool_search_file(
    state: AppState,
    path: str,
    pattern: str,
    max_matches: int = 20,
    context_lines: int = 2,
    ignore_case: bool = False,
) -> str:
    """Search a file with a regex; return matching lines with context and line numbers."""
    try:
        p = resolve_tool_path(state, path)
    except ValueError as exc:
        return f"Error: {exc}"
    if not p.is_file():
        return f"Error: {path} is not a file (resolved: {p})."
    if not pattern:
        return "Error: pattern is required."

    flags = re.MULTILINE
    if ignore_case:
        flags |= re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as exc:
        return f"Error: invalid regex: {exc}"

    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"Error reading {path}: {exc}"

    hits: list[int] = []
    for i, line in enumerate(lines, start=1):
        if regex.search(line):
            hits.append(i)
            if len(hits) >= max_matches:
                break

    if not hits:
        return f"No matches for /{pattern}/ in {p.resolve()}"

    ctx = max(0, int(context_lines))
    blocks: list[str] = [
        f"File: {p.resolve()} | {len(hits)} match(es) (showing up to {max_matches})"
    ]
    for line_no in hits:
        lo = max(1, line_no - ctx)
        hi = min(len(lines), line_no + ctx)
        blocks.append(f"--- match at line {line_no} ---")
        for n in range(lo, hi + 1):
            mark = ">" if n == line_no else " "
            blocks.append(f"{mark}{n}|{lines[n - 1]}")
    return "\n".join(blocks)


def tool_list_dir(state: AppState, path: str) -> str:
    try:
        p = resolve_tool_path(state, path)
    except ValueError as exc:
        return f"Error: {exc}"
    if not p.is_dir():
        return f"Error: {path} is not a directory (resolved: {p})."
    entries = []
    for child in sorted(p.iterdir()):
        kind = "dir " if child.is_dir() else "file"
        entries.append(f"{kind}  {child.name}")
    return "\n".join(entries) if entries else "(empty)"


def tool_write_file(state: AppState, path: str, content: str) -> str:
    """Create or overwrite a UTF-8 text file. Parent dirs are created as needed."""
    try:
        p = resolve_tool_path(state, path)
    except ValueError as exc:
        return f"Error: {exc}"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
    except OSError as exc:
        return f"Error writing {path} (resolved: {p}): {exc}"
    return f"Wrote {len(content)} chars to {p}"


def tool_str_replace(
    state: AppState, path: str, old_string: str, new_string: str
) -> str:
    """Replace exactly one occurrence of old_string with new_string in a file."""
    try:
        p = resolve_tool_path(state, path)
    except ValueError as exc:
        return f"Error: {exc}"
    if not p.is_file():
        return f"Error: {path} is not a file (resolved: {p})."
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading {path}: {exc}"

    count = text.count(old_string)
    if count == 0:
        return (
            "Error: old_string not found. Whitespace/indentation must match exactly. "
            "Use search_file to locate the spot, then read_file(start_line, end_line) "
            "and copy old_string verbatim (without LINE| prefixes)."
        )
    if count > 1:
        return (
            f"Error: old_string matched {count} times; must match exactly once. "
            "Include more surrounding lines to make it unique."
        )

    updated = text.replace(old_string, new_string, 1)
    try:
        p.write_text(updated, encoding="utf-8", newline="\n")
    except OSError as exc:
        return f"Error writing {path}: {exc}"
    return f"Replaced 1 occurrence in {p} ({len(old_string)} -> {len(new_string)} chars)."
