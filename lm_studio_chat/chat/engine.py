"""Streaming chat loop with multi-round tool calling."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Iterator, TextIO

from lm_studio_chat.config import (
    MAX_EMPTY_CONTINUES,
    MAX_TOKENS,
    MAX_TOOL_ROUNDS,
    TEMPERATURE,
)
from lm_studio_chat.logging import log_write
from lm_studio_chat.state import (
    AppState,
    ToolContext,
    clear_active_llm_stream,
    register_active_llm_stream,
)
from lm_studio_chat.tools.registry import (
    available_tool_schemas,
    dispatch_tool,
    sanitize_tool_args_for_ui,
    tool_activity_summary,
    truncate_tool_result,
)
from lm_studio_chat.types import ChatPartial, ToolResult


def completion_limit_kwargs(state: AppState) -> dict[str, int]:
    """Provider-specific token limit field for chat.completions.create."""
    param = state.provider.completion_tokens_param
    return {param: MAX_TOKENS}


def create_completion_stream(
    state: AppState,
    *,
    model_id: str,
    messages: list[dict[str, Any]],
) -> Any:
    """Open a streaming completion, with fallbacks for optional API parameters."""
    token_variants: list[dict[str, int]] = [completion_limit_kwargs(state)]
    if state.provider.completion_tokens_param == "max_tokens":
        token_variants.append({"max_completion_tokens": MAX_TOKENS})

    if state.provider.omit_temperature:
        sampling_variants: list[dict[str, Any]] = [{}]
    else:
        temperature = (
            TEMPERATURE
            if state.provider.temperature is None
            else state.provider.temperature
        )
        sampling_variants = [
            {"temperature": temperature},
            {},
        ]
    usage_variants: list[dict[str, Any]] = (
        [{"stream_options": {"include_usage": True}}, {}]
        if state.provider.stream_usage
        else [{}]
    )

    last_exc: Exception | None = None
    for token_kw in token_variants:
        for sampling_kw in sampling_variants:
            for usage_kw in usage_variants:
                kwargs: dict[str, Any] = {
                    "model": model_id,
                    "messages": messages,
                    "tools": available_tool_schemas(),
                    "stream": True,
                    **token_kw,
                    **sampling_kw,
                    **usage_kw,
                    **state.provider.extra_completion_kwargs,
                }
                try:
                    return state.client.chat.completions.create(**kwargs)
                except Exception as exc:
                    last_exc = exc
    assert last_exc is not None
    raise last_exc


def delta_text_field(delta: Any, *names: str) -> str:
    """Pull a string field from a streaming delta (incl. vendor extras)."""
    for name in names:
        val = getattr(delta, name, None)
        if isinstance(val, str) and val:
            return val
    extra = getattr(delta, "model_extra", None)
    if isinstance(extra, dict):
        for name in names:
            val = extra.get(name)
            if isinstance(val, str) and val:
                return val
    return ""


def reasoning_snippet(text: str, max_len: int = 140) -> str:
    """Short user-facing summary of model reasoning for the activity timeline."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    for i, ch in enumerate(cleaned):
        if ch in ".!?" and i >= 24:
            sentence = cleaned[: i + 1]
            if len(sentence) <= max_len:
                return sentence
            break
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[: max_len - 1].rsplit(" ", 1)[0]
    return f"{cut}…" if cut else f"{cleaned[: max_len - 1]}…"


def run_chat(
    state: AppState,
    model_id: str,
    messages: list[dict[str, Any]],
    log_fh: TextIO | None = None,
    should_cancel: Callable[[], bool] | None = None,
    session_id: str | None = None,
) -> Iterator[ChatPartial]:
    """Yield growing assistant content and tool activity for the current user turn.

    Handles up to MAX_TOOL_ROUNDS of tool_call -> tool_result -> re-inference.
    """
    visible = ""
    tool_events: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    segment_index: dict[str, int] = {}
    current_text_seg_id: str | None = None
    tools_ran = False
    empty_continues = 0
    turn_start = time.monotonic()
    thinking_id: str | None = None
    last_thinking_yield = 0.0
    tool_activity_ids: dict[str, str] = {}

    def _cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    def _now_ms() -> int:
        return int((time.monotonic() - turn_start) * 1000)

    def _status_segments() -> list[dict[str, Any]]:
        return [s for s in segments if s.get("type") == "status"]

    def _emit(extra: str = "") -> ChatPartial:
        return ChatPartial(
            content=visible + extra,
            tool_events=list(tool_events),
            activity=_status_segments(),
            segments=list(segments),
        )

    def _set_segment(seg_id: str, **fields: Any) -> None:
        idx = segment_index.get(seg_id)
        if idx is None:
            return
        segments[idx].update(fields)

    def _rebuild_segment_index() -> None:
        segment_index.clear()
        for i, seg in enumerate(segments):
            seg_id = seg.get("id")
            if seg_id:
                segment_index[seg_id] = i

    def _close_text_segment() -> None:
        nonlocal current_text_seg_id
        if current_text_seg_id is not None:
            idx = segment_index.get(current_text_seg_id)
            if idx is not None:
                content = str(segments[idx].get("content") or "")
                if not content.strip():
                    segments.pop(idx)
                    _rebuild_segment_index()
        current_text_seg_id = None

    def _append_content(piece: str) -> None:
        nonlocal visible, current_text_seg_id
        if not piece:
            return
        visible += piece
        _end_thinking()
        if current_text_seg_id is None:
            if not piece.strip():
                return
            seg_id = f"text-{len(segments)}"
            segments.append(
                {
                    "type": "text",
                    "id": seg_id,
                    "content": piece,
                    "elapsed_ms": _now_ms(),
                }
            )
            segment_index[seg_id] = len(segments) - 1
            current_text_seg_id = seg_id
        else:
            idx = segment_index[current_text_seg_id]
            segments[idx]["content"] = str(segments[idx].get("content") or "") + piece

    def _start_thinking() -> None:
        nonlocal thinking_id
        if thinking_id is not None:
            return
        act_id = f"think-{len(segments)}"
        segments.append(
            {
                "type": "status",
                "id": act_id,
                "kind": "thinking",
                "label": "Thinking…",
                "elapsed_ms": _now_ms(),
                "active": True,
            }
        )
        segment_index[act_id] = len(segments) - 1
        thinking_id = act_id

    def _update_thinking_snippet(reasoning: str) -> bool:
        if thinking_id is None:
            return False
        idx = segment_index.get(thinking_id)
        if idx is None:
            return False
        snippet = reasoning_snippet(reasoning)
        prev = str(segments[idx].get("snippet") or "")
        if snippet:
            _set_segment(thinking_id, snippet=snippet)
        return snippet != prev

    def _end_thinking() -> None:
        nonlocal thinking_id
        if thinking_id is None:
            return
        idx = segment_index.get(thinking_id)
        fields: dict[str, Any] = {"active": False, "elapsed_ms": _now_ms()}
        if idx is not None:
            seg = segments[idx]
            snippet = str(seg.get("snippet") or "")
            if not snippet:
                snippet = reasoning_snippet(str(seg.pop("_reasoning", "") or ""))
            seg.pop("_reasoning", None)
            if snippet:
                fields["snippet"] = snippet
                fields["label"] = snippet
            else:
                fields["label"] = "Thought briefly"
        _set_segment(thinking_id, **fields)
        thinking_id = None

    def _touch_thinking() -> bool:
        nonlocal last_thinking_yield
        if thinking_id is None:
            return False
        _set_segment(thinking_id, elapsed_ms=_now_ms())
        now = time.monotonic()
        if (now - last_thinking_yield) >= 0.3:
            last_thinking_yield = now
            return True
        return False

    def _ensure_tool_planned(tc_id: str, name: str, args: dict[str, Any]) -> str:
        if tc_id in tool_activity_ids:
            act_id = tool_activity_ids[tc_id]
            _set_segment(
                act_id,
                name=name,
                arguments=sanitize_tool_args_for_ui(name, args),
                label=f"Planning {tool_activity_summary(name, args)}",
                elapsed_ms=_now_ms(),
            )
            return act_id
        act_id = f"tool-{tc_id or len(segments)}"
        segments.append(
            {
                "type": "status",
                "id": act_id,
                "kind": "tool_planned",
                "name": name,
                "arguments": sanitize_tool_args_for_ui(name, args),
                "label": f"Planning {tool_activity_summary(name, args)}",
                "elapsed_ms": _now_ms(),
                "active": True,
                "tool_call_id": tc_id,
            }
        )
        segment_index[act_id] = len(segments) - 1
        tool_activity_ids[tc_id] = act_id
        return act_id

    def _mark_tool_running(act_id: str, name: str, args: dict[str, Any]) -> None:
        _set_segment(
            act_id,
            kind="tool_running",
            name=name,
            arguments=sanitize_tool_args_for_ui(name, args),
            label=f"Running {tool_activity_summary(name, args)}",
            elapsed_ms=_now_ms(),
            active=True,
        )

    def _mark_tool_done(
        act_id: str,
        name: str,
        args: dict[str, Any],
        result: str,
        ok: bool,
    ) -> None:
        prefix = "✓" if ok else "✗"
        _set_segment(
            act_id,
            kind="tool_done",
            name=name,
            arguments=sanitize_tool_args_for_ui(name, args),
            result=truncate_tool_result(result),
            ok=ok,
            label=f"{prefix} {tool_activity_summary(name, args)}",
            elapsed_ms=_now_ms(),
            active=False,
        )

    def _finalize_active_activity() -> None:
        for entry in segments:
            if entry.get("type") == "status" and entry.get("active"):
                entry["active"] = False
                entry["elapsed_ms"] = _now_ms()

    def _close_stream(stream: Any) -> None:
        close = getattr(stream, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    for round_idx in range(MAX_TOOL_ROUNDS):
        if _cancelled():
            log_write(log_fh, "--- stopped: user cancelled ---\n")
            _finalize_active_activity()
            suffix = "\n\n_(stopped)_" if visible else "_(stopped)_"
            yield _emit(suffix)
            return

        stream = create_completion_stream(
            state,
            model_id=model_id,
            messages=messages,
        )

        register_active_llm_stream(state, stream)

        content_buf = ""
        reasoning_buf = ""
        tool_calls_accum: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage_info: dict[str, Any] | None = None
        cancelled_mid_stream = False
        stream_dirty = False

        _close_text_segment()
        _start_thinking()
        yield _emit()

        try:
            for chunk in stream:
                if _cancelled():
                    cancelled_mid_stream = True
                    break

                if getattr(chunk, "usage", None) is not None:
                    usage = chunk.usage
                    usage_info = {
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    }
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                chunk_dirty = False

                reasoning_piece = delta_text_field(
                    delta, "reasoning_content", "reasoning", "reasoning_text"
                )
                if reasoning_piece:
                    reasoning_buf += reasoning_piece
                    _start_thinking()
                    if thinking_id is not None:
                        _set_segment(thinking_id, _reasoning=reasoning_buf)
                    snippet_changed = _update_thinking_snippet(reasoning_buf)
                    if snippet_changed or _touch_thinking():
                        chunk_dirty = True

                if delta.content:
                    content_buf += delta.content
                    _append_content(delta.content)
                    chunk_dirty = True

                if delta.tool_calls:
                    _update_thinking_snippet(reasoning_buf)
                    _end_thinking()
                    _close_text_segment()
                    for tc in delta.tool_calls:
                        slot = tool_calls_accum.setdefault(
                            tc.index,
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                slot["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                slot["function"]["arguments"] += tc.function.arguments
                        tc_id = slot["id"] or f"idx-{tc.index}"
                        name = slot["function"]["name"] or "tool"
                        try:
                            parsed_args = json.loads(
                                slot["function"]["arguments"] or "{}"
                            )
                        except json.JSONDecodeError:
                            parsed_args = {}
                        _ensure_tool_planned(tc_id, name, parsed_args)
                    chunk_dirty = True

                if chunk_dirty:
                    stream_dirty = True
                    yield _emit()
        finally:
            clear_active_llm_stream(state, stream)
            if cancelled_mid_stream:
                _close_stream(stream)

        if stream_dirty and not cancelled_mid_stream:
            _update_thinking_snippet(reasoning_buf)
            _end_thinking()
            _close_text_segment()
            yield _emit()

        if cancelled_mid_stream:
            log_write(
                log_fh,
                (
                    f"--- round {round_idx} (cancelled mid-stream) ---\n"
                    f"content so far:\n{content_buf if content_buf else '(empty)'}\n"
                ),
            )
            _finalize_active_activity()
            yield _emit("\n\n_(stopped)_")
            return

        tool_calls_list = [tool_calls_accum[i] for i in sorted(tool_calls_accum)]
        log_write(
            log_fh,
            (
                f"--- round {round_idx} ---\n"
                f"finish_reason: {finish_reason!r}\n"
                f"usage: {json.dumps(usage_info) if usage_info else 'n/a'}\n"
                f"reasoning:\n{reasoning_buf if reasoning_buf else '(empty)'}\n"
                f"content:\n{content_buf if content_buf else '(empty)'}\n"
                f"tool_calls:\n"
                f"{json.dumps(tool_calls_list, indent=2) if tool_calls_list else '(none)'}\n"
            ),
        )

        if usage_info is not None and session_id:
            state.session_usage[session_id] = usage_info

        if not tool_calls_accum:
            _end_thinking()
            _close_text_segment()
            if (
                tools_ran
                and not content_buf.strip()
                and empty_continues < MAX_EMPTY_CONTINUES
            ):
                empty_continues += 1
                log_write(
                    log_fh,
                    (
                        f"--- empty stop after tools; continue nudge "
                        f"{empty_continues}/{MAX_EMPTY_CONTINUES} ---\n"
                    ),
                )
                messages.append(
                    {"role": "assistant", "content": content_buf or ""}
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You stopped without a tool call or a final answer. "
                            "Continue the user's task now: call the next needed "
                            "tool (usually str_replace), or briefly confirm what "
                            "you changed / why you cannot."
                        ),
                    }
                )
                yield _emit()
                continue
            yield _emit()
            return

        _end_thinking()
        _close_text_segment()

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": content_buf or None,
            "tool_calls": tool_calls_list,
        }
        messages.append(assistant_msg)
        tools_ran = True
        empty_continues = 0

        pending_injections: list[Any] = []

        for tc in assistant_msg["tool_calls"]:
            if _cancelled():
                log_write(log_fh, "--- stopped: user cancelled before tool run ---\n")
                _finalize_active_activity()
                yield _emit("\n\n_(stopped)_")
                return

            name = tc["function"]["name"]
            args_json = tc["function"]["arguments"]
            try:
                parsed_args = json.loads(args_json or "{}")
            except json.JSONDecodeError:
                parsed_args = {}

            tc_id = tc["id"] or f"idx-{name}-{len(tool_events)}"
            act_id = tool_activity_ids.get(tc_id) or _ensure_tool_planned(
                tc_id, name, parsed_args
            )
            _mark_tool_running(act_id, name, parsed_args)
            yield _emit()

            result = dispatch_tool(
                name, args_json, ctx=ToolContext(state, session_id)
            )
            tool_text = result.text if isinstance(result, ToolResult) else result
            if isinstance(result, ToolResult) and result.inject_user_content is not None:
                pending_injections.append(result.inject_user_content)

            tool_ok = not str(tool_text).startswith("Error")
            _mark_tool_done(act_id, name, parsed_args, str(tool_text), tool_ok)
            tool_events.append(
                {
                    "name": name,
                    "arguments": sanitize_tool_args_for_ui(name, parsed_args),
                    "result": truncate_tool_result(tool_text),
                    "ok": tool_ok,
                }
            )
            yield _emit()

            if _cancelled():
                log_write(
                    log_fh,
                    (
                        f"--- tool result (after cancel): {name} ---\n"
                        f"arguments:\n{args_json}\n"
                        f"result:\n{tool_text}\n"
                        "--- stopped: user cancelled ---\n"
                    ),
                )
                _finalize_active_activity()
                yield _emit("\n\n_(stopped)_")
                return

            log_write(
                log_fh,
                (
                    f"--- tool result: {name} ---\n"
                    f"arguments:\n{args_json}\n"
                    f"result:\n{tool_text}\n"
                ),
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_text,
                }
            )

        for inject in pending_injections:
            messages.append({"role": "user", "content": inject})
            log_write(log_fh, "--- injected attachment image into model context ---\n")

        continue

    log_write(log_fh, "--- stopped: reached MAX_TOOL_ROUNDS ---\n")
    yield _emit("\n\n_(Reached tool-use limit; stopping.)_")
