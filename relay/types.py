"""Shared dataclasses for tools and chat streaming."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ToolResult:
    """Tool output; optional multimodal user content injected before the next model turn."""

    text: str
    inject_user_content: Any | None = None


@dataclass
class ChatPartial:
    """Streaming update for one assistant turn (visible text + tool activity)."""

    content: str
    tool_events: list[dict[str, Any]]
    activity: list[dict[str, Any]]
    segments: list[dict[str, Any]]
    # Token usage summed over every model call so far this turn (see chat/usage.py); None before the first call.
    usage: dict[str, int] | None = None


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str
    path: Path
    skill_dir: Path
