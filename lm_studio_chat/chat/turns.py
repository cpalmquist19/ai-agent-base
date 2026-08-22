"""User turn orchestration: history replay, attachments, streaming."""

from __future__ import annotations

import datetime as dt
import time
from typing import Any, Iterator, TextIO

from lm_studio_chat.chat.engine import run_chat
from lm_studio_chat.chat.prompts import build_system_prompt
from lm_studio_chat.config import MAX_TOKENS
from lm_studio_chat.logging import log_write, open_session_log
from lm_studio_chat.sessions.attachments import (
    history_attachment_note,
    recent_image_reinjection,
)
from lm_studio_chat.skills.discovery import skill_api_prefix
from lm_studio_chat.state import AppState


def run_user_turn(
    state: AppState,
    model_id: str,
    history: list[dict[str, Any]],
    user_message: str,
    session_id: str | None = None,
    api_user_content: Any | None = None,
    user_attachments: list[dict[str, Any]] | None = None,
    user_skill: str | None = None,
) -> Iterator[list[dict[str, Any]]]:
    """Yield growing chat history (list of {role, content}) as the model responds."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt(state)}
    ]
    for entry in history:
        role = entry.get("role")
        content = entry.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        if role == "user":
            content += history_attachment_note(entry.get("attachments") or [])
            skill_name = entry.get("skill")
            if isinstance(skill_name, str) and skill_name.strip():
                content = skill_api_prefix(skill_name.strip()) + content
        messages.append({"role": role, "content": content})

    final_content: Any = api_user_content if api_user_content is not None else user_message
    current_has_image = isinstance(api_user_content, list)
    reinjected: dict[str, Any] | None = None
    if not current_has_image and session_id:
        reinjected = recent_image_reinjection(state, session_id, history)
    if reinjected is not None:
        base_text = final_content if isinstance(final_content, str) else user_message
        final_content = [
            {"type": "text", "text": base_text},
            {
                "type": "text",
                "text": (
                    f"[Re-attached the most recent image '{reinjected['name']}' "
                    f"(id: {reinjected['id']}) so you can refer to it directly.]"
                ),
            },
            reinjected["part"],
        ]
    messages.append({"role": "user", "content": final_content})

    log_fh: TextIO | None = None
    if session_id:
        try:
            log_fh = open_session_log(session_id)
            log_write(
                log_fh,
                (
                    f"\n{'=' * 72}\n"
                    f"turn_started: {dt.datetime.now().astimezone().isoformat(timespec='seconds')}\n"
                    f"model: {model_id}\n"
                    f"max_tokens: {MAX_TOKENS}\n"
                    f"user_message (ui):\n{user_message}\n"
                    f"api_user_content:\n{api_user_content if api_user_content is not None else user_message}\n"
                    + (
                        f"reinjected_image: {reinjected['name']} (id: {reinjected['id']})\n"
                        if reinjected is not None
                        else ""
                    )
                ),
            )
        except OSError as exc:
            print(f"Warning: could not open model log: {exc}")
            log_fh = None

    user_entry: dict[str, Any] = {"role": "user", "content": user_message}
    if user_attachments:
        user_entry["attachments"] = user_attachments
    if user_skill:
        user_entry["skill"] = user_skill
    working = history + [
        user_entry,
        {"role": "assistant", "content": "", "tool_events": [], "activity": [], "segments": []},
    ]
    turn_start = time.monotonic()
    try:
        for partial in run_chat(
            state,
            model_id,
            messages,
            log_fh=log_fh,
            should_cancel=state.cancel.is_set,
            session_id=session_id,
        ):
            working[-1]["content"] = partial.content
            working[-1]["tool_events"] = partial.tool_events
            working[-1]["activity"] = partial.activity
            working[-1]["segments"] = partial.segments
            yield list(working)
        working[-1]["elapsed_ms"] = int((time.monotonic() - turn_start) * 1000)
        yield list(working)
        log_write(
            log_fh,
            f"turn_finished: {dt.datetime.now().astimezone().isoformat(timespec='seconds')}\n"
            f"elapsed_ms: {working[-1]['elapsed_ms']}\n",
        )
    finally:
        if log_fh is not None:
            try:
                log_fh.close()
            except OSError:
                pass
