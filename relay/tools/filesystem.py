"""Filesystem tools: read, search, list, write, str_replace."""

from __future__ import annotations

import os
import re
from pathlib import Path

from relay.config import allow_unrestricted_paths
from relay.state import AppState


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


def resolve_tool_path(state: AppState, path: str) -> Path:
    """Resolve a file/dir path for tool I/O, confined to the project root (or shell cwd) by default."""
    raw = path.strip()
    if not raw:
        raise ValueError("empty path")
    expanded = Path(os.path.expandvars(raw)).expanduser()
    if not expanded.is_absolute():
        base = state.project_root if state.project_root is not None else state.shell_cwd
        expanded = base / expanded
    resolved = expanded.resolve()

    if allow_unrestricted_paths():
        return resolved

    root = (state.project_root or state.shell_cwd).resolve()
    if not _is_relative_to(resolved, root):
        target_label = "the open project" if state.project_root is not None else "the working directory"
        raise ValueError(f"path is outside {target_label}: {raw} (resolved: {resolved})")

    return resolved


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


_SKIP_DIRS = frozenset(
    {".git", ".hg", ".svn", "node_modules", "__pycache__", "venv", ".venv", ".idea", ".vscode", ".pytest_cache", ".mypy_cache"}
)
_MAX_SEARCH_FILE_BYTES = 1_000_000


def _search_folder(root: Path, regex: re.Pattern[str], pattern: str, max_matches: int) -> str:
    """Grep-style search under a folder: 'relative/path:line|text', skipping binaries and junk folders."""
    matches: list[str] = []
    files_scanned = 0
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            file_path = Path(dirpath) / name
            try:
                if file_path.stat().st_size > _MAX_SEARCH_FILE_BYTES:
                    continue
                data = file_path.read_bytes()
            except OSError:
                continue
            if b"\x00" in data[:4096]:  # binary file
                continue
            files_scanned += 1
            for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{file_path.relative_to(root).as_posix()}:{number}|{line.strip()[:200]}")
                    if len(matches) >= max_matches:
                        truncated = True
                        break
            if truncated:
                break
        if truncated:
            break

    if not matches:
        return f"No matches for /{pattern}/ in {files_scanned} text file(s) under {root.resolve()}"
    header = f"Folder: {root.resolve()} | {len(matches)} match(es) in {files_scanned} file(s) scanned"
    if truncated:
        header += f" (stopped at max_matches={max_matches})"
    footer = "Pass a single file path to search_file or read_file for surrounding context."
    return "\n".join([header, *matches, footer])


def tool_search_file(
    state: AppState,
    path: str,
    pattern: str,
    max_matches: int = 20,
    context_lines: int = 2,
    ignore_case: bool = False,
) -> str:
    """Search a file (or every text file under a folder) with a regex."""
    try:
        p = resolve_tool_path(state, path)
    except ValueError as exc:
        return f"Error: {exc}"
    if not p.is_file() and not p.is_dir():
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

    if p.is_dir():
        return _search_folder(p, regex, pattern, max_matches)

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


def _nul_error(what: str) -> str:
    return (
        f"Error: {what} contains a NUL character (U+0000). Text files can't hold one, and it almost always "
        "means a unicode escape was mangled: source code that should keep a backslash-u escape arrived "
        "as a NUL followed by hex digits. Nothing was written. Send the real character, or double the "
        "backslash in the JSON to put a backslash-u escape into the file."
    )


def tool_write_file(state: AppState, path: str, content: str) -> str:
    """Create or overwrite a UTF-8 text file. Parent dirs are created as needed."""
    if "\x00" in content:
        return _nul_error("content")
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
    if "\x00" in new_string:
        return _nul_error("new_string")
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
