"""Streaming chat SSE route."""

from __future__ import annotations

from typing import Any, Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from lm_studio_chat.chat.turns import run_user_turn
from lm_studio_chat.models import ChatRequest
from lm_studio_chat.sessions.attachments import (
    compose_user_message,
    persist_uploaded_attachments,
    validate_attachments,
)
from lm_studio_chat.sessions.store import (
    find_session,
    load_sessions,
    new_session,
    save_sessions,
    session_title,
    sessions_summary,
)
from lm_studio_chat.skills.discovery import resolve_skill_name
from lm_studio_chat.sse import sse
from lm_studio_chat.state import AppState


def create_chat_router(state: AppState) -> APIRouter:
    router = APIRouter()

    @router.post("/api/chat")
    def api_chat(body: ChatRequest) -> StreamingResponse:
        raw_message = (body.message or "").strip()
        attachments = list(body.attachments or [])
        skill_raw = (body.skill or "").strip()
        skill_name = resolve_skill_name(skill_raw) if skill_raw else None
        if skill_raw and skill_name is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown skill: {skill_raw}",
            )
        if not raw_message and not attachments and not skill_name:
            raise HTTPException(
                status_code=400,
                detail="Message, attachment, or skill is required",
            )
        if not state.model_id:
            raise HTTPException(status_code=503, detail="Model not ready")

        validate_attachments(attachments)

        with state.sessions_lock:
            sessions = load_sessions()
            session_id = body.session_id
            session = find_session(sessions, session_id) if session_id else None
            if session is None:
                session = new_session()
                session_id = session["id"]
                sessions.append(session)

            stored = (
                persist_uploaded_attachments(session, attachments) if attachments else []
            )
            user_message, api_user_content, user_attachments = compose_user_message(
                session_id,
                raw_message,
                stored,
                skill=skill_name,
                supports_vision=getattr(state.provider, "supports_vision", False),
            )
            if session.get("title") in (None, "", "New chat"):
                session["title"] = session_title(
                    [{"role": "user", "content": user_message}]
                )
            save_sessions(sessions)
            history = list(session.get("messages") or [])

        model_id = state.model_id
        assert session_id is not None

        def event_stream() -> Iterator[str]:
            state.cancel.clear()
            final_history = history
            try:
                yield sse(
                    {
                        "type": "started",
                        "session_id": session_id,
                        "title": session_title(
                            [{"role": "user", "content": user_message}]
                        ),
                    }
                )
                for updated in run_user_turn(
                    state,
                    model_id,
                    history,
                    user_message,
                    session_id=session_id,
                    api_user_content=api_user_content,
                    user_attachments=user_attachments,
                    user_skill=skill_name,
                ):
                    final_history = updated
                    yield sse(
                        {
                            "type": "content",
                            "session_id": session_id,
                            "messages": updated,
                        }
                    )

                usage = state.session_usage.get(session_id)
                with state.sessions_lock:
                    sessions_now = load_sessions()
                    sess = find_session(sessions_now, session_id)
                    if sess is not None:
                        sess["messages"] = final_history
                        if usage is not None:
                            sess["usage"] = usage
                        if sess.get("title") in (None, "", "New chat"):
                            sess["title"] = session_title(final_history)
                        save_sessions(sessions_now)
                        title = sess.get("title") or "Untitled"
                    else:
                        title = session_title(final_history)

                yield sse(
                    {
                        "type": "done",
                        "session_id": session_id,
                        "messages": final_history,
                        "title": title,
                        "usage": usage,
                        "sessions": sessions_summary(load_sessions()),
                    }
                )
            except Exception as exc:
                print(f"Turn error: {exc}")
                err_text = f"\n\n**Error:** `{exc}`"
                if (
                    final_history
                    and final_history[-1].get("role") == "assistant"
                ):
                    final_history = list(final_history)
                    final_history[-1] = {
                        **final_history[-1],
                        "content": (final_history[-1].get("content") or "") + err_text,
                    }
                else:
                    user_err_entry: dict[str, Any] = {
                        "role": "user",
                        "content": user_message,
                    }
                    if user_attachments:
                        user_err_entry["attachments"] = user_attachments
                    if skill_name:
                        user_err_entry["skill"] = skill_name
                    final_history = list(final_history) + [
                        user_err_entry,
                        {"role": "assistant", "content": err_text.strip()},
                    ]
                with state.sessions_lock:
                    sessions_now = load_sessions()
                    sess = find_session(sessions_now, session_id)
                    if sess is not None:
                        sess["messages"] = final_history
                        save_sessions(sessions_now)
                yield sse(
                    {
                        "type": "error",
                        "session_id": session_id,
                        "message": str(exc),
                        "messages": final_history,
                        "sessions": sessions_summary(load_sessions()),
                    }
                )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
