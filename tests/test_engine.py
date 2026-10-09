"""Behaviour of the multi-round tool-calling loop, driven by a scripted model."""

from __future__ import annotations

import threading
import time

import pytest

from evals.fake import EMPTY, call, say
from lm_studio_chat.config import MAX_EMPTY_CONTINUES, MAX_TOOL_ROUNDS
from lm_studio_chat.tools.shell import kill_active_command, tool_run_command
from tests.conftest import drive


def _tool_messages(messages):
    return [m for m in messages if m.get("role") == "tool"]


def test_runs_tool_then_answers(make_state, tmp_path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    state, client = make_state([call("list_dir", path="."), say("done")])
    final, messages = drive(state)
    assert final.content == "done"
    assert [e["name"] for e in final.tool_events] == ["list_dir"]
    assert final.tool_events[0]["ok"] is True
    assert "a.txt" in _tool_messages(messages)[0]["content"]
    assert client.calls_made == 2


def test_tool_arguments_split_across_chunks_are_reassembled(make_state, tmp_path):
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    state, _ = make_state([call("read_file", path="note.txt"), say("ok")])
    _, messages = drive(state)
    assert "hello" in _tool_messages(messages)[0]["content"]


def test_empty_reply_after_tools_gets_a_nudge_then_recovers(make_state):
    state, client = make_state([call("get_current_time"), EMPTY, say("all done")])
    final, messages = drive(state)
    assert final.content == "all done"
    assert client.calls_made == 3
    assert any("You stopped without a tool call" in str(m.get("content")) for m in messages if m["role"] == "user")


def test_empty_reply_nudges_are_capped(make_state):
    steps = [call("get_current_time")] + [EMPTY] * (MAX_EMPTY_CONTINUES + 1)
    state, client = make_state(steps)
    final, _ = drive(state)
    assert final.content == ""
    assert client.calls_made == len(steps)  # gave up instead of looping forever


def test_empty_reply_before_any_tool_is_not_nudged(make_state):
    state, client = make_state([EMPTY])
    final, _ = drive(state)
    assert final.content == ""
    assert client.calls_made == 1


def test_stops_at_round_limit(make_state):
    state, client = make_state([call("get_current_time")] * (MAX_TOOL_ROUNDS + 1))
    final, _ = drive(state)
    assert client.calls_made == MAX_TOOL_ROUNDS
    assert "Reached tool-use limit" in final.content


def test_malformed_tool_json_becomes_an_error_result_not_a_crash(make_state):
    state, _ = make_state([{"tool_calls": [{"name": "read_file", "arguments": "{not json"}]}, say("recovered")])
    final, messages = drive(state)
    assert final.content == "recovered"
    assert _tool_messages(messages)[0]["content"].startswith("Error: invalid JSON")
    assert final.tool_events[0]["ok"] is False


def test_unknown_tool_is_reported_to_the_model(make_state):
    state, _ = make_state([call("delete_everything"), say("ok")])
    _, messages = drive(state)
    assert "unknown tool" in _tool_messages(messages)[0]["content"]


def test_missing_required_argument_is_reported_to_the_model(make_state):
    state, _ = make_state([call("read_file"), say("ok")])
    _, messages = drive(state)
    assert _tool_messages(messages)[0]["content"].startswith("Error: bad arguments for read_file")


def test_several_tool_calls_in_one_turn_all_run_in_order(make_state, tmp_path):
    from evals.fake import calls

    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    state, _ = make_state([calls(call("list_dir", path="."), call("get_current_time")), say("ok")])
    final, _ = drive(state)
    assert [e["name"] for e in final.tool_events] == ["list_dir", "get_current_time"]


def test_cancel_stops_before_the_next_model_call(make_state):
    state, client = make_state([call("get_current_time"), say("never reached")])
    messages_ref = {}

    def cancel_after_first_tool() -> bool:
        msgs = messages_ref.get("m", [])
        return any(m.get("role") == "tool" for m in msgs)

    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "go"}]
    messages_ref["m"] = messages
    from lm_studio_chat.chat.engine import run_chat

    final = None
    for partial in run_chat(state, "scripted", messages, should_cancel=cancel_after_first_tool):
        final = partial
    assert "(stopped)" in final.content
    assert client.calls_made == 1


def test_unsupported_stream_options_falls_back_to_a_plain_request(make_state):
    state, client = make_state([say("hi")], stream_usage=True, reject_params=("stream_options",))
    final, _ = drive(state)
    assert final.content == "hi"
    assert "stream_options" not in client.requests[0]["kwargs"]


def test_falls_back_to_max_completion_tokens_when_max_tokens_is_rejected(make_state):
    state, client = make_state([say("hi")], reject_params=("max_tokens",))
    final, _ = drive(state)
    assert final.content == "hi"
    assert "max_completion_tokens" in client.requests[0]["kwargs"]


def test_script_exhaustion_surfaces_as_an_error(make_state):
    from evals.fake import ScriptExhausted

    state, _ = make_state([])
    with pytest.raises(ScriptExhausted):
        drive(state)


@pytest.mark.skipif(not hasattr(time, "monotonic"), reason="n/a")
def test_stop_kills_a_running_shell_command(make_state):
    state, _ = make_state([])
    finished = threading.Event()

    def run():
        tool_run_command(state, 'python -c "import time; time.sleep(30)"', timeout_seconds=60)
        finished.set()

    worker = threading.Thread(target=run, daemon=True)
    started = time.monotonic()
    worker.start()
    deadline = started + 10
    while state.active_command_proc is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert state.active_command_proc is not None, "command never started"
    kill_active_command(state)
    assert finished.wait(timeout=10), "run_command did not return after the kill"
    assert time.monotonic() - started < 25
