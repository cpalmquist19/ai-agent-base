"""Chat attachment storage, validation, and view_attachment tool."""

from __future__ import annotations

import base64
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from relay.config import (
    ATTACHMENTS_DIR,
    IMAGE_EXTENSIONS,
    IMAGE_MIME_BY_EXT,
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_IMAGE_ATTACHMENT_BYTES,
    MAX_TEXT_ATTACHMENT_BYTES,
    TEXT_FILE_EXTENSIONS,
)
from relay.models import ChatAttachment
from relay.sessions.store import find_session, load_sessions
from relay.skills.discovery import skill_api_prefix
from relay.state import AppState, ToolContext
from relay.types import ToolResult


def safe_session_dir_name(session_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_id) or "unknown"


def attachment_disk_path(session_id: str, att_id: str, ext: str) -> Path:
    suffix = ext if ext.startswith(".") else (f".{ext}" if ext else "")
    return ATTACHMENTS_DIR / safe_session_dir_name(session_id) / f"{att_id}{suffix}"


def attachment_image_url(path: Path, mime: str | None, ext: str) -> str:
    """Return the ``image_url.url`` value LM Studio accepts.

    LM Studio requires a ``data:image/...;base64,...`` URI (raw base64 alone
    yields "Invalid url."). It also rejects ``image/webp`` and ``image/avif`` in
    the prefix even when the bytes are valid — use ``image/png`` instead
    (lmstudio-bug-tracker #1027).
    """
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    m = (mime or "").strip().lower()
    if not m.startswith("image/"):
        normalized = ext if ext.startswith(".") else f".{ext}"
        m = IMAGE_MIME_BY_EXT.get(normalized, "image/png")
    if m in ("image/webp", "image/avif"):
        m = "image/png"
    return f"data:{m};base64,{b64}"


def attachment_ext(name: str) -> str:
    return Path(name or "").suffix.lower()


def delete_session_attachments(session_id: str) -> None:
    folder = ATTACHMENTS_DIR / safe_session_dir_name(session_id)
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)


def validate_attachments(attachments: list[ChatAttachment]) -> None:
    if len(attachments) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_ATTACHMENTS_PER_MESSAGE} attachments per message.",
        )
    for att in attachments:
        name = (att.name or "").strip()
        if not name or "/" in name or "\\" in name or ".." in name:
            raise HTTPException(status_code=400, detail="Invalid attachment name.")
        ext = attachment_ext(name)
        if att.kind == "image":
            if ext not in IMAGE_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Blocked image type: {name}",
                )
            raw_b64 = (att.data_base64 or "").strip()
            if not raw_b64:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image attachment missing data: {name}",
                )
            try:
                raw = base64.b64decode(raw_b64, validate=True)
            except Exception:
                try:
                    raw = base64.b64decode(raw_b64)
                except Exception as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid image data for {name}: {exc}",
                    ) from exc
            if len(raw) > MAX_IMAGE_ATTACHMENT_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image too large (max 20 MB): {name}",
                )
        else:
            if ext not in TEXT_FILE_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Blocked file type: {name}",
                )
            if att.text is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"File attachment missing text: {name}",
                )
            if len(att.text.encode("utf-8", errors="replace")) > MAX_TEXT_ATTACHMENT_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large (max 512 KB): {name}",
                )


def persist_uploaded_attachments(
    session: dict[str, Any],
    uploads: list[ChatAttachment],
) -> list[dict[str, Any]]:
    """Save uploads to disk and register them on the session. Returns stored records."""
    session_id = session["id"]
    session.setdefault("attachments", {})
    stored: list[dict[str, Any]] = []

    for att in uploads:
        att_id = uuid.uuid4().hex[:12]
        name = att.name.strip()
        ext = attachment_ext(name)
        path = attachment_disk_path(session_id, att_id, ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        mime = (att.mime or "").strip().lower()

        if att.kind == "image":
            b64 = (att.data_base64 or "").strip()
            if b64.startswith("data:"):
                b64 = b64.split(",", 1)[-1]
            path.write_bytes(base64.b64decode(b64))
            if not mime.startswith("image/"):
                mime = IMAGE_MIME_BY_EXT.get(ext, "image/png")
        else:
            path.write_text(att.text or "", encoding="utf-8")
            if not mime:
                mime = "text/plain"

        record = {
            "id": att_id,
            "kind": att.kind,
            "name": name,
            "mime": mime,
            "ext": ext,
        }
        session["attachments"][att_id] = record
        stored.append(record)

    return stored


def compose_user_message(
    session_id: str,
    message: str,
    stored: list[dict[str, Any]],
    skill: str | None = None,
    supports_vision: bool = True,
) -> tuple[str, Any, list[dict[str, Any]]]:
    """Build UI text, API content (str or multimodal list), and attachment meta."""
    ui_parts: list[str] = []
    api_parts: list[str] = []
    if message.strip():
        ui_parts.append(message.strip())
        api_parts.append(message.strip())

    if skill:
        prefix = skill_api_prefix(skill)
        api_parts.insert(0, prefix.rstrip())
        if not api_parts[1:]:
            api_parts.append("Follow the selected Agent Skill.")

    image_parts: list[dict[str, Any]] = []
    for rec in stored:
        att_id = rec["id"]
        name = rec["name"]
        ext = rec.get("ext") or attachment_ext(name)
        if rec["kind"] == "file":
            path = attachment_disk_path(session_id, att_id, ext)
            body = path.read_text(encoding="utf-8")
            lang = ext.lstrip(".") or "text"
            api_parts.append(
                f"Attached file `{name}` (id: {att_id}):\n```{lang}\n{body}\n```"
            )
        else:
            if supports_vision:
                api_parts.append(f"[Attached image: {name}] (id: {att_id})")
                path = attachment_disk_path(session_id, att_id, ext)
                url = attachment_image_url(path, rec.get("mime"), ext)
                image_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": url},
                    }
                )
            else:
                api_parts.append(
                    f"[Attached image: {name} (id: {att_id}). This model cannot view images; describe it in text or switch to a vision model.]"
                )

    ui_message = "\n\n".join(ui_parts).strip()
    api_text = "\n\n".join(api_parts).strip()
    if not api_text:
        api_text = "(attachment only)"

    ui_attachments = [
        {
            "id": rec["id"],
            "kind": rec["kind"],
            "name": rec["name"],
            "mime": rec.get("mime"),
        }
        for rec in stored
    ]

    if image_parts:
        api_content: Any = [{"type": "text", "text": api_text}, *image_parts]
        return ui_message, api_content, ui_attachments
    return ui_message, api_text, ui_attachments


def history_attachment_note(attachments: list[dict[str, Any]]) -> str:
    """A compact reminder that an earlier turn's uploads are retrievable by id."""
    refs: list[str] = []
    for att in attachments or []:
        att_id = att.get("id")
        if not att_id:
            continue
        kind = att.get("kind") or "attachment"
        name = att.get("name") or att_id
        refs.append(f"{kind} `{name}` (id: {att_id})")
    if not refs:
        return ""
    return (
        "\n\n[Attachments from this turn are no longer in your view. To inspect "
        "one again, call view_attachment(id): " + "; ".join(refs) + "]"
    )


def recent_image_reinjection(
    state: AppState, session_id: str, history: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Multimodal image part for the most recent prior user turn's image, if any."""
    if not getattr(state.provider, "supports_vision", False):
        return None
    last_user: dict[str, Any] | None = None
    for entry in reversed(history):
        if entry.get("role") == "user":
            last_user = entry
            break
    if not last_user:
        return None
    images = [
        a
        for a in (last_user.get("attachments") or [])
        if a.get("kind") == "image" and a.get("id")
    ]
    if not images:
        return None
    att = images[-1]
    with state.sessions_lock:
        session = find_session(load_sessions(), session_id)
        rec = (session.get("attachments") or {}).get(att["id"]) if session else None
    if not rec:
        return None
    ext = rec.get("ext") or attachment_ext(rec.get("name") or "")
    path = attachment_disk_path(session_id, att["id"], ext)
    if not path.is_file():
        return None
    try:
        url = attachment_image_url(path, rec.get("mime"), ext)
    except OSError:
        return None
    return {
        "id": att["id"],
        "name": rec.get("name") or att["id"],
        "part": {"type": "image_url", "image_url": {"url": url}},
    }


def tool_view_attachment(ctx: ToolContext, attachment_id: str) -> str | ToolResult:
    """Load a previously uploaded chat attachment by id."""
    state = ctx.state
    session_id = ctx.session_id
    if not session_id:
        return "Error: no active chat session."
    att_id = (attachment_id or "").strip()
    if not att_id:
        return "Error: attachment_id is required."

    with state.sessions_lock:
        session = find_session(load_sessions(), session_id)
        if session is None:
            return "Error: session not found."
        att = (session.get("attachments") or {}).get(att_id)
    if not att:
        return f"Error: attachment '{att_id}' not found in this chat."

    path = attachment_disk_path(session_id, att_id, att.get("ext", ""))
    if not path.is_file():
        return f"Error: attachment file missing for '{att_id}'."

    name = att.get("name") or att_id
    if att.get("kind") == "file":
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as exc:
            return f"Error reading attachment '{att_id}': {exc}"
        if len(body.encode("utf-8", errors="replace")) > MAX_TEXT_ATTACHMENT_BYTES:
            body = body[:MAX_TEXT_ATTACHMENT_BYTES] + "\n...(truncated)"
        lang = (att.get("ext") or ".txt").lstrip(".") or "text"
        return (
            f"Attachment '{name}' (id: {att_id}):\n"
            f"```{lang}\n{body}\n```"
        )

    if not getattr(state.provider, "supports_vision", False):
        return (
            f"Attached image '{name}' (id: {att_id}) is on disk, but this model "
            "cannot view images. Describe the image in text or switch to a vision model."
        )

    image_url = attachment_image_url(path, att.get("mime"), att.get("ext", ""))
    return ToolResult(
        text=(
            f"Loaded image '{name}' (id: {att_id}). "
            "The image is attached below for your analysis."
        ),
        inject_user_content=[
            {"type": "text", "text": f"[Attachment {att_id}: {name}]"},
            {"type": "image_url", "image_url": {"url": image_url}},
        ],
    )
