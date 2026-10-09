"""Environment overrides, paths, and application constants."""

from __future__ import annotations

import os
import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
_APP_ROOT = APP_ROOT

try:
    from dotenv import load_dotenv

    load_dotenv(APP_ROOT / ".env")
except ImportError:
    pass

HISTORY_FILE = Path.home() / ".lm_studio_chat_history.json"
PROJECT_FILE = Path.home() / ".lm_studio_chat_project.json"
LOG_DIR = Path.home() / ".lm_studio_chat_logs"
ATTACHMENTS_DIR = Path.home() / ".lm_studio_chat_attachments"
STATIC_DIR = APP_ROOT / "static"
_DEFAULT_SKILLS_DIRS = (
    APP_ROOT / "skills",
    Path.home() / ".lm_studio_chat" / "skills",
)
APP_HOST = os.getenv("LM_STUDIO_CHAT_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("LM_STUDIO_CHAT_PORT", "7860"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "lm_studio").strip().lower()

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "")
UNSLOTH_BASE_URL = os.getenv("UNSLOTH_BASE_URL", "http://127.0.0.1:8000/v1")
UNSLOTH_API_KEY = os.getenv("UNSLOTH_API_KEY", "sk-no-key-required")

MAX_TOKENS = int(os.getenv("LM_STUDIO_MAX_TOKENS", "32768"))
TEMPERATURE = float(os.getenv("LM_STUDIO_TEMPERATURE", "0.3"))

def allow_unrestricted_paths() -> bool:
    """Return True if path sandboxing is disabled via environment variable."""
    val = os.getenv("LM_STUDIO_ALLOW_UNRESTRICTED_PATHS", "").strip().lower()
    return val in ("1", "true", "yes")


SYSTEM_PROMPT = (
    "You are a local coding assistant with tools. Tool rounds are limited — be efficient.\n"
    "\n"
    "Honesty and grounding (non-negotiable):\n"
    "- Only state facts that appear in tool results or the user's message.\n"
    "- If tool output lacks a detail (temperature, date, number, quote, etc.), say "
    "so plainly. Do NOT invent, estimate, or fill gaps from 'typical' knowledge "
    "and present them as observed facts.\n"
    "- Prefer 'I don't know' / 'the search/page did not include that' over a "
    "confident guess.\n"
    "- Distinguish clearly: quoted/tool-backed facts vs. your own inference. "
    "Never blend them.\n"
    "- For live web facts (weather, news, prices, docs): web_search finds URLs; "
    "then fetch_url to read the page before answering. Snippets alone are not "
    "enough when the user needs specific numbers or details.\n"
    "- When the user gives a specific http(s) URL, call fetch_url on it directly "
    "— no web_search needed. Summarize or answer from the returned page text.\n"
    "- Cite the URL(s) you actually used. If you only have snippets, say that "
    "and share the links instead of fabricating page content.\n"
    "\n"
    "Code-edit workflow:\n"
    "1) search_file(pattern) to find the spot (line numbers). Prefer this over "
    "re-reading a whole file or using run_command/grep.\n"
    "2) read_file(path, start_line, end_line) for a small window around that spot. "
    "Do not re-read the same file from line 1 repeatedly.\n"
    "3) str_replace with old_string copied EXACTLY from the read (same indentation "
    "and whitespace). Prefer str_replace for existing files; write_file only for "
    "new files or full rewrites.\n"
    "4) Paths: relative paths resolve under the open project root (or working directory). "
    "Paths outside the open project are rejected unless unrestricted paths are enabled. "
    "When confirming a change, always cite the full resolved path from the tool "
    "result (not just the relative path you passed in).\n"
    "5) If str_replace fails, search/read again — do not revert a successful edit "
    "to try a different approach unless that edit was wrong.\n"
    "6) When the task is done, stop calling tools and briefly confirm what changed.\n"
    "\n"
    "After every tool result you MUST either call the next tool or write a short "
    "final answer. Never end with an empty message.\n"
    "Also: list_dir to explore; run_command for shell/git (cwd persists); "
    "fetch_url for a URL the user gives or after web_search; "
    "web_search when you need to find pages. "
    "Answer directly when tools are not needed.\n"
    "\n"
    "Agent Skills:\n"
    "- Reusable task procedures are listed at the end of this prompt (name + "
    "description only).\n"
    "- Call list_skills() to see every available skill; read_skill(name) loads "
    "full instructions.\n"
    "- When a request matches a skill — or the user selects one in the UI — call "
    "read_skill(name) FIRST, then follow its workflow using your tools.\n"
    "- Skills describe how; tools fetch, inspect, and write files.\n"
)

VISION_SYSTEM_PROMPT_BLOCK = (
    "\nChat attachments (you CAN see images):\n"
    "- You are a vision-capable model. When an image is in the current message "
    "you can see it directly — describe it; never claim you cannot view images.\n"
    "- User uploads include an attachment id, e.g. (id: abc123).\n"
    "- To save context, images from EARLIER turns are not kept in view. Those "
    "turns are marked '[Attachments from this turn are no longer in your view … "
    "(id: abc123)]'. That means the image still exists — it is NOT gone.\n"
    "- If the user asks about an image or file you were shown earlier and it is "
    "not currently visible, CALL view_attachment(id) to load it again, THEN "
    "answer. Do not say you can't see it and do not guess its contents.\n"
    "- view_attachment re-injects images into your vision context and returns "
    "text file contents inline; both are legitimate grounded sources.\n"
    "- Never retroactively claim a correct answer you gave about an attachment "
    "was fabricated. If unsure what you saw, re-open it with view_attachment(id) "
    "instead of disavowing it.\n"
    "- Do not call view_attachment for something the user just attached in the "
    "same turn unless you need to re-check it after other edits.\n"
)

MAX_TOOL_ROUNDS = 12
MAX_EMPTY_CONTINUES = 2
COMMAND_OUTPUT_LIMIT = 50_000
WEB_SEARCH_RESULT_LIMIT = 8
FETCH_URL_MAX_CHARS = 20_000
FETCH_URL_TIMEOUT_SECONDS = 20
FETCH_URL_USER_AGENT = (
    "Mozilla/5.0 (compatible; LMStudioChat/1.0; +local-assistant)"
)
INSPECT_PAGE_TIMEOUT_MS = 30_000
INSPECT_PAGE_CONTENT_WAIT_MS = 20_000
INSPECT_PAGE_MAX_CHARS = 30_000
INSPECT_PAGE_INTERACTIVE_ROLES = frozenset(
    {
        "textbox",
        "button",
        "checkbox",
        "radio",
        "combobox",
        "link",
        "searchbox",
        "switch",
        "tab",
        "menuitem",
        "option",
        "slider",
        "spinbutton",
    }
)
INSPECT_PAGE_KEEP_WHEN_FILTERING = INSPECT_PAGE_INTERACTIVE_ROLES | frozenset({"heading"})
INSPECT_PAGE_BOT_CHALLENGE_TITLES = (
    "azure waf",
    "attention required",
    "just a moment",
    "checking your browser",
    "access denied",
)
INSPECT_PAGE_BOT_CHALLENGE_SNIPPETS = (
    "checking you're not a bot",
    "checking if you are a bot",
    "verify you are human",
    "cloudflare",
    "captcha",
    "challenge-platform",
)
_SKILL_FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n", re.DOTALL)

_EXPLORER_SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".next",
        ".cache",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
        ".eggs",
    }
)

IMAGE_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
        ".avif",
    }
)
TEXT_FILE_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".rst",
        ".csv",
        ".tsv",
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".xml",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".jsx",
        ".py",
        ".pyi",
        ".rb",
        ".php",
        ".java",
        ".kt",
        ".kts",
        ".go",
        ".rs",
        ".c",
        ".h",
        ".cpp",
        ".cc",
        ".cxx",
        ".hpp",
        ".hxx",
        ".cs",
        ".swift",
        ".m",
        ".mm",
        ".scala",
        ".lua",
        ".r",
        ".pl",
        ".pm",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".sql",
        ".vue",
        ".svelte",
        ".dart",
        ".zig",
        ".nim",
        ".proto",
        ".graphql",
        ".gql",
        ".tf",
        ".hcl",
        ".cmake",
        ".mk",
        ".makefile",
        ".dockerfile",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".gitignore",
        ".editorconfig",
        ".properties",
    }
)
MAX_TEXT_ATTACHMENT_BYTES = 512 * 1024
MAX_IMAGE_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_ATTACHMENTS_PER_MESSAGE = 8

IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".avif": "image/avif",
}
