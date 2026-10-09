"""Tool registry: schemas, dispatch, and UI helpers."""

from __future__ import annotations

import json
from typing import Any, Callable

from lm_studio_chat.sessions.attachments import tool_view_attachment
from lm_studio_chat.skills.discovery import tool_list_skills, tool_read_skill
from lm_studio_chat.state import ToolContext
from lm_studio_chat.tools.builtin import tool_calculate, tool_get_current_time
from lm_studio_chat.tools.filesystem import (
    tool_list_dir,
    tool_read_file,
    tool_search_file,
    tool_str_replace,
    tool_write_file,
)
from lm_studio_chat.tools.inspect_page import (
    inspect_page_available,
    tool_inspect_page,
)
from lm_studio_chat.tools.schemas import TOOL_SCHEMAS
from lm_studio_chat.tools.shell import tool_run_command
from lm_studio_chat.tools.web import (
    tool_fetch_url,
    tool_web_search,
    web_search_available,
)
from lm_studio_chat.types import ToolResult

STATE_TOOLS = frozenset(
    {
        "search_file",
        "read_file",
        "list_dir",
        "write_file",
        "str_replace",
        "run_command",
        "inspect_page",
    }
)

TOOL_IMPLS: dict[str, Callable[..., str | ToolResult]] = {
    "get_current_time": tool_get_current_time,
    "calculate": tool_calculate,
    "search_file": tool_search_file,
    "read_file": tool_read_file,
    "list_dir": tool_list_dir,
    "write_file": tool_write_file,
    "str_replace": tool_str_replace,
    "run_command": tool_run_command,
    "web_search": tool_web_search,
    "fetch_url": tool_fetch_url,
    "inspect_page": tool_inspect_page,
    "read_skill": tool_read_skill,
    "list_skills": tool_list_skills,
    "view_attachment": tool_view_attachment,
}


def sanitize_tool_args_for_ui(name: str, args: dict[str, Any]) -> dict[str, Any]:
    out = dict(args)
    for key in ("content", "new_string", "old_string", "command", "expression"):
        val = out.get(key)
        if isinstance(val, str) and len(val) > 300:
            out[key] = f"{val[:300]}... ({len(val)} chars total)"
    return out


def tool_activity_summary(name: str, args: dict[str, Any]) -> str:
    """Short human-readable label for a tool call in the activity timeline."""
    path = args.get("path") or args.get("url") or args.get("expression") or args.get(
        "attachment_id"
    )
    if path:
        return f"{name} → {path}"
    command = args.get("command")
    if command:
        cmd = str(command)
        return f"{name} → {cmd[:72] + '…' if len(cmd) > 72 else cmd}"
    pattern = args.get("pattern")
    if pattern:
        return f"{name} → /{pattern}/"
    return name or "tool"


def truncate_tool_result(text: str, limit: int = 800) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text)} chars total)"


def dispatch_tool(name: str, arguments_json: str, *, ctx: ToolContext) -> str | ToolResult:
    fn = TOOL_IMPLS.get(name)
    if fn is None:
        return f"Error: unknown tool '{name}'."
    try:
        args = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as exc:
        return f"Error: invalid JSON in tool arguments: {exc}"
    try:
        if name == "view_attachment":
            return tool_view_attachment(ctx, **args)
        if name in STATE_TOOLS:
            result = fn(ctx.state, **args)
        else:
            result = fn(**args)
        return result if isinstance(result, ToolResult) else str(result)
    except TypeError as exc:
        return f"Error: bad arguments for {name}: {exc}"
    except Exception as exc:
        return f"Error while running {name}: {exc}"


def probe_tool_availability(name: str) -> tuple[bool, str | None]:
    if name == "web_search":
        return web_search_available()
    if name == "inspect_page":
        return inspect_page_available()
    return True, None


def tool_catalog() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for schema in TOOL_SCHEMAS:
        fn = schema.get("function") or {}
        name = fn.get("name")
        if not name:
            continue
        available, unavailable_reason = probe_tool_availability(name)
        tools.append(
            {
                "name": name,
                "description": (fn.get("description") or "").strip(),
                "available": available,
                "unavailable_reason": unavailable_reason,
            }
        )
    return tools


def available_tool_schemas() -> list[dict[str, Any]]:
    catalog = {t["name"]: t["available"] for t in tool_catalog()}
    return [
        s
        for s in TOOL_SCHEMAS
        if catalog.get((s.get("function") or {}).get("name"), True)
    ]
