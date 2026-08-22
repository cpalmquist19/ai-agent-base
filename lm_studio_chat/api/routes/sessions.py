"""Chat session CRUD, stop, and log routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from lm_studio_chat.config import LOG_DIR
from lm_studio_chat.logging import (
    ensure_log_dir,
    reveal_in_file_manager,
    session_log_path,
)
from lm_studio_chat.models import OpenLogRequest, StopRequest
from lm_studio_chat.sessions.attachments import (
    attachment_disk_path,
    delete_session_attachments,
)
from lm_studio_chat.sessions.store import (
    find_session,
    load_sessions,
    mark_stopped,
    new_session,
    save_sessions,
    sessions_summary,
)
from lm_studio_chat.state import AppState, close_active_llm_stream
from lm_studio_chat.tools.shell import kill_active_command


def create_sessions_router(state: AppState) -> APIRouter:
    router = APIRouter()

    @router.get("/api/sessions")
    def api_list_sessions() -> dict[str, Any]:
        with state.sessions_lock:
            sessions = load_sessions()
            return {"sessions": sessions_summary(sessions)}

    @router.get("/api/sessions/{session_id}")
    def api_get_session(session_id: str) -> dict[str, Any]:
        with state.sessions_lock:
            session = find_session(load_sessions(), session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "id": session["id"],
            "title": session.get("title") or "Untitled",
            "created": session.get("created"),
            "messages": list(session.get("messages") or []),
            "usage": session.get("usage") or state.session_usage.get(session["id"]),
        }

    @router.get("/api/sessions/{session_id}/attachments/{attachment_id}")
    def api_get_attachment(session_id: str, attachment_id: str) -> FileResponse:
        with state.sessions_lock:
            session = find_session(load_sessions(), session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        att = (session.get("attachments") or {}).get(attachment_id)
        if att is None:
            raise HTTPException(status_code=404, detail="Attachment not found")
        path = attachment_disk_path(session_id, attachment_id, att.get("ext", ""))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Attachment file missing")
        return FileResponse(
            path,
            media_type=att.get("mime") or "application/octet-stream",
            filename=att.get("name"),
        )

    @router.post("/api/sessions")
    def api_create_session() -> dict[str, Any]:
        session = new_session()
        with state.sessions_lock:
            sessions = load_sessions()
            sessions.append(session)
            save_sessions(sessions)
        return {
            "id": session["id"],
            "title": session["title"],
            "created": session["created"],
            "messages": [],
        }

    @router.delete("/api/sessions/{session_id}")
    def api_delete_session(session_id: str) -> dict[str, Any]:
        with state.sessions_lock:
            sessions = load_sessions()
            if find_session(sessions, session_id) is None:
                raise HTTPException(status_code=404, detail="Session not found")
            sessions = [s for s in sessions if s["id"] != session_id]
            save_sessions(sessions)
        delete_session_attachments(session_id)
        return {"ok": True, "sessions": sessions_summary(sessions)}

    @router.delete("/api/sessions")
    def api_clear_sessions() -> dict[str, Any]:
        with state.sessions_lock:
            sessions = load_sessions()
            for session in sessions:
                delete_session_attachments(session["id"])
            save_sessions([])
        return {"ok": True, "sessions": []}

    @router.post("/api/stop")
    def api_stop(body: StopRequest) -> dict[str, Any]:
        state.cancel.set()
        close_active_llm_stream(state)
        kill_active_command(state)
        messages = mark_stopped(body.messages)
        if body.session_id:
            with state.sessions_lock:
                sessions = load_sessions()
                session = find_session(sessions, body.session_id)
                if session is not None:
                    session["messages"] = messages
                    save_sessions(sessions)
        return {"ok": True, "messages": messages}

    @router.post("/api/open-log")
    def api_open_log(body: OpenLogRequest) -> dict[str, str]:
        if body.session_id:
            path = session_log_path(body.session_id)
            if not path.is_file():
                ensure_log_dir()
                return {
                    "message": (
                        f"No log yet for this chat (`{path.name}`). "
                        f"Send a message first — folder: `{LOG_DIR}`"
                    )
                }
            return {"message": reveal_in_file_manager(path)}
        ensure_log_dir()
        return {
            "message": (
                reveal_in_file_manager(LOG_DIR)
                + " (no active chat; opened logs folder)"
            )
        }

    return router
