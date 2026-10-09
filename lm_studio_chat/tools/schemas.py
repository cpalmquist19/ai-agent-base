"""OpenAI function-calling schemas for registered tools."""

from __future__ import annotations

from typing import Any

from lm_studio_chat.config import (
    FETCH_URL_MAX_CHARS,
    INSPECT_PAGE_MAX_CHARS,
    WEB_SEARCH_RESULT_LIMIT,
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current local date/time in ISO 8601 format.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate a math expression using Python syntax and the `math` "
                "module. Example expressions: 'sqrt(2) * pi', '2**10', 'log(1000, 10)'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression to evaluate."}
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_file",
            "description": (
                "Search a text file with a regex pattern. Returns matching lines "
                "with line numbers and nearby context. Use this FIRST to locate "
                "edit sites instead of reading the whole file or using shell grep."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Absolute or relative file path. Relative paths resolve "
                            "against the open project working directory."
                        ),
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Python regex (or literal text) to find.",
                    },
                    "max_matches": {
                        "type": "integer",
                        "description": "Max matches to return (default 20).",
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Extra lines before/after each match (default 2).",
                    },
                    "ignore_case": {
                        "type": "boolean",
                        "description": "Case-insensitive search (default false).",
                    },
                },
                "required": ["path", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a slice of a UTF-8 text file by 1-based line numbers. "
                "Prefer search_file first, then read a small window with "
                "start_line/end_line. Lines are prefixed with 'N|' for navigation; "
                "omit those prefixes when copying into str_replace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Absolute or relative file path. Relative paths resolve "
                            "against the open project working directory."
                        ),
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "First line to return (1-based, default 1).",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to return (inclusive). Defaults to EOF.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Hard cap on returned characters (default 30000).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List the entries of a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Absolute or relative directory path. Relative paths "
                            "resolve against the open project working directory."
                        ),
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create or overwrite a UTF-8 text file with the given content. "
                "Creates parent directories if needed. Prefer str_replace for small "
                "edits to existing files; use write_file for new files or full rewrites."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Absolute or relative file path. Relative paths resolve "
                            "against the open project working directory."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file contents to write.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "str_replace",
            "description": (
                "Replace exactly one occurrence of old_string with new_string in a "
                "text file. old_string must match uniquely with exact whitespace. "
                "Prefer this over write_file for surgical code changes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Absolute or relative file path. Relative paths resolve "
                            "against the open project working directory."
                        ),
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Exact text to find (must appear exactly once).",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a local shell command (Windows cmd/PowerShell syntax). "
                "Examples: 'dir', 'cd C:\\\\Code\\\\ai-agent', 'git status'. "
                "Do NOT use this to search/edit files — use search_file / "
                "str_replace instead. A bare 'cd <path>' persists for later commands."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Max seconds to wait (default 60).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the live web via DuckDuckGo. Returns titles, URLs, and "
                "SHORT snippets only — not full page content. Never invent facts "
                "missing from snippets. For weather, news, docs, or any specific "
                "numbers/details, follow up with fetch_url on the best result URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": (
                            f"Number of results to return (1-{WEB_SEARCH_RESULT_LIMIT}, "
                            "default 5)."
                        ),
                    },
                    "region": {
                        "type": "string",
                        "description": (
                            "DuckDuckGo region code, e.g. us-en, uk-en (default us-en)."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "Fetch a web page by URL and return extracted plain text. Use when "
                "the user provides a link, or after web_search when you need facts "
                "from the page itself (weather, docs, articles). Only report details "
                "present in the returned text; say so if a detail is missing. Some "
                "sites are JS-only or block bots."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full http(s) URL to fetch.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": (
                            f"Max characters of extracted text to return "
                            f"(default {FETCH_URL_MAX_CHARS})."
                        ),
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_page",
            "description": (
                "Render a URL in Chromium (headless by default, headed when "
                "configured) and capture the accessibility tree (Playwright aria_snapshot) "
                "for test automation and Page Object generation. Waits up to 20s for "
                "interactive elements before snapshotting. Prefer scope='form' for login "
                "pages or scope='main' to reduce noise."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full http(s) URL to inspect.",
                    },
                    "scope": {
                        "type": "string",
                        "description": (
                            "Landmark to snapshot: 'main' (default), 'form', "
                            "or 'full'. Falls back to filtered full-page snapshot "
                            "when the landmark is missing."
                        ),
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": (
                            f"Max characters of output to return "
                            f"(default {INSPECT_PAGE_MAX_CHARS})."
                        ),
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": (
                "List all available Agent Skills (name and short description). "
                "Use when the user asks what skills exist or before choosing a "
                "skill. Follow up with read_skill(name) to load instructions."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": (
                "Load the full instructions for a named Agent Skill. Call this "
                "when the user's task matches a skill listed in the system prompt "
                "(e.g. playwright-page-object), then follow the skill's workflow."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name from the Available Agent Skills list.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_attachment",
            "description": (
                "Load a previously uploaded chat attachment by its id (shown in "
                "user messages as '(id: abc123)'). Call this when you need to "
                "re-examine an earlier image or text file — especially on "
                "follow-up questions about a prior upload. Images are injected "
                "into your vision context; text files return their contents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "attachment_id": {
                        "type": "string",
                        "description": (
                            "Attachment id from the user's message, e.g. abc123."
                        ),
                    },
                },
                "required": ["attachment_id"],
            },
        },
    },
]
