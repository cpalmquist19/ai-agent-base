"""Chat session JSON persistence and CRUD helpers."""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

from relay.config import HISTORY_FILE


def load_sessions() -> list[dict[str, Any]]:
    if not HISTORY_FILE.is_file():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    sessions = data.get("sessions", []) if isinstance(data, dict) else []
    return [s for s in sessions if isinstance(s, dict) and "id" in s]


def save_sessions(sessions: list[dict[str, Any]]) -> None:
    try:
        HISTORY_FILE.write_text(
            json.dumps({"sessions": sessions}, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"Warning: could not save chat history: {exc}")


def find_session(
    sessions: list[dict[str, Any]], session_id: str | None
) -> dict[str, Any] | None:
    if not session_id:
        return None
    for s in sessions:
        if s["id"] == session_id:
            return s
    return None


def session_title(messages: list[dict[str, Any]]) -> str:
    for m in messages:
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str) and content.strip():
            text = content.strip().splitlines()[0]
            return text[:60] + ("..." if len(text) > 60 else "")
        attachments = m.get("attachments") or []
        if attachments:
            name = attachments[0].get("name") or "Attachment"
            label = f"Attachment: {name}"
            return label[:60] + ("..." if len(label) > 60 else "")
    return "New chat"


def sessions_summary(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(sessions, key=lambda s: s.get("created", ""), reverse=True)
    return [
        {
            "id": s["id"],
            "title": s.get("title") or "Untitled",
            "created": s.get("created"),
        }
        for s in ordered
    ]


def new_session(title: str = "New chat") -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "title": title,
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "messages": [],
    }


def mark_stopped(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    history = list(history or [])
    if history and history[-1].get("role") == "assistant":
        content = history[-1].get("content") or ""
        if "_(stopped)_" not in content:
            history[-1] = {
                **history[-1],
                "content": (content + "\n\n_(stopped)_").lstrip(),
            }
    return history
