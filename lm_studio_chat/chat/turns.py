"""User turn orchestration: history replay, attachments, streaming."""

from __future__ import annotations

import datetime as dt
import time
from typing import Any, Iterator, TextIO

from lm_studio_chat.chat.engine import run_chat
from lm_studio_chat.chat.prompts import build_system_prompt
from lm_studio_chat.config import MAX_TOKENS
from lm_studio_chat.lm_client import effective_context_window, fetch_context_capacity
from lm_studio_chat.logging import log_write, open_session_log
from lm_studio_chat.sessions.attachments import (
    history_attachment_note,
    recent_image_reinjection,
)
from lm_studio_chat.skills.discovery import skill_api_prefix
from lm_studio_chat.state import AppState


def estimate_tokens(content: Any) -> int:
    """Rough estimation of token count (chars / 4)."""
    if isinstance(content, str):
        return max(1, len(content) // 4)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict):
                part_type = part.get("type")
                if part_type == "text":
                    total += len(str(part.get("text") or "")) // 4
                elif part_type == "image_url":
                    total += 1000
            elif isinstance(part, str):
                total += len(part) // 4
        return max(1, total)
    if isinstance(content, dict):
        return max(1, len(str(content)) // 4)
    return 1


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(estimate_tokens(m.get("content")) + 4 for m in messages)


def resolve_context_budget(state: AppState) -> tuple[int, int]:
    """Returns (context_window, input_budget)."""
    window = state.context_window
    if window is None and state.provider.local:
        caps = fetch_context_capacity(state.model_id)
        window = effective_context_window(caps)
        if window is not None:
            state.context_window = window

    if window is None:
        window = 128_000 if state.provider.id == "openai" else 16_384

    output_budget = (
        min(MAX_TOKENS, max(1024, int(window * 0.25)))
        if window <= MAX_TOKENS + 1024
        else MAX_TOKENS
    )
    tool_reserve = 1000
    budget = max(512, window - output_budget - tool_reserve)
    return window, budget


def trim_messages_for_context(
    state: AppState, messages: list[dict[str, Any]], log_fh: TextIO | None = None
) -> list[dict[str, Any]]:
    """Trim oldest user+assistant pairs from history to fit context window budget."""
    if len(messages) <= 2:
        window, budget = resolve_context_budget(state)
        if estimate_messages_tokens(messages) > budget:
            raise ValueError("This message is too large for the model context window.")
        return messages

    window, budget = resolve_context_budget(state)
    system_msg = messages[0]
    current_msg = messages[-1]

    # If system prompt + current turn alone exceeds budget, fail immediately
    if estimate_messages_tokens([system_msg, current_msg]) > budget:
        raise ValueError("This message is too large for the model context window.")

    if estimate_messages_tokens(messages) <= budget:
        return messages

    history_turns = [dict(m) for m in messages[1:-1]]
    trimmed = False

    while history_turns:
        candidate = [system_msg] + history_turns + [current_msg]
        if estimate_messages_tokens(candidate) <= budget:
            break
        drop_count = 2 if len(history_turns) >= 2 else 1
        history_turns = history_turns[drop_count:]
        trimmed = True

    if estimate_messages_tokens([system_msg] + history_turns + [current_msg]) > budget:
        if history_turns:
            history_turns = []
            trimmed = True
        if estimate_messages_tokens([system_msg, current_msg]) > budget:
            raise ValueError("This message is too large for the model context window.")

    if trimmed:
        note = "[Older messages omitted to fit the context window.]"
        if history_turns:
            first = dict(history_turns[0])
            if isinstance(first.get("content"), str):
                first["content"] = f"{note}\n\n{first['content']}"
            history_turns[0] = first
        else:
            if isinstance(current_msg.get("content"), str):
                current_msg = dict(current_msg)
                current_msg["content"] = f"{note}\n\n{current_msg['content']}"
            elif isinstance(current_msg.get("content"), list):
                current_msg = dict(current_msg)
                current_msg["content"] = [{"type": "text", "text": f"{note}\n\n"}] + list(
                    current_msg["content"]
                )
        if log_fh is not None:
            log_write(
                log_fh,
                f"history_trimmed: context_window={window}, budget={budget}, retained_history_msgs={len(history_turns)}\n",
            )

    return [system_msg] + history_turns + [current_msg]


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
    messages = trim_messages_for_context(state, messages, log_fh=log_fh)

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
