"""Behaviour of the multi-round tool-calling loop, driven by a scripted model."""

from __future__ import annotations

import os
import subprocess
import threading
import time

import pytest

from evals.fake import EMPTY, call, say
from relay.config import MAX_EMPTY_CONTINUES, MAX_TOOL_ROUNDS
from relay.tools.shell import kill_active_command, tool_run_command
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


def test_gemini_style_stream_keeps_parallel_calls_apart_and_echoes_the_signature(make_state, tmp_path):
    """No index on the deltas, and Gemini 3 rejects the next request without its thought_signature."""
    from evals.fake import gemini_calls

    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    state, client = make_state(
        [gemini_calls(call("list_dir", path="."), call("get_current_time")), say("ok")]
    )
    final, messages = drive(state)
    assert [e["name"] for e in final.tool_events] == ["list_dir", "get_current_time"]
    assert final.content == "ok"
    sent = [m for m in client.requests[1]["kwargs"]["messages"] if m.get("role") == "assistant"][-1]
    assert [tc["function"]["name"] for tc in sent["tool_calls"]] == ["list_dir", "get_current_time"]
    assert sent["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "sig_1"}}
    assert "extra_content" not in sent["tool_calls"][1]


def test_tool_call_slot_uses_index_when_the_stream_provides_one():
    from relay.chat.engine import tool_call_slot

    assert tool_call_slot(1, "call_a", {0: {"id": "call_a"}}) == 1
    assert tool_call_slot(0, None, {0: {"id": "call_a"}}) == 0


def test_tool_call_slot_separates_calls_by_id_when_index_is_missing():
    """Gemini's OpenAI-compatible stream sends index=None with one whole call per chunk."""
    from relay.chat.engine import tool_call_slot

    accum: dict[int, dict] = {}
    for call_id in ("call_a", "call_b"):
        accum.setdefault(tool_call_slot(None, call_id, accum), {"id": call_id})
    assert list(accum) == [0, 1]
    assert tool_call_slot(None, "call_a", accum) == 0  # a repeated id continues its own call
    assert tool_call_slot(None, None, accum) == 1  # no id and no index: the latest call


def test_cancel_stops_before_the_next_model_call(make_state):
    state, client = make_state([call("get_current_time"), say("never reached")])
    messages_ref = {}

    def cancel_after_first_tool() -> bool:
        msgs = messages_ref.get("m", [])
        return any(m.get("role") == "tool" for m in msgs)

    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "go"}]
    messages_ref["m"] = messages
    from relay.chat.engine import run_chat

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


def test_omit_temperature_is_not_sent(make_state):
    state, client = make_state([say("hi")], omit_temperature=True)
    final, _ = drive(state)
    assert final.content == "hi"
    assert "temperature" not in client.requests[0]["kwargs"]


def test_provider_temperature_overrides_the_global_default(make_state):
    state, client = make_state([say("hi")], temperature=0.2)
    drive(state)
    assert client.requests[0]["kwargs"]["temperature"] == 0.2


def test_declared_context_window_is_used_for_cloud_providers(make_state):
    from relay.chat.turns import resolve_context_budget

    state, _ = make_state([], local=False, context_window=200_000)
    window, budget = resolve_context_budget(state)
    assert window == 200_000
    assert budget < window


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


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
        return str(pid) in out
    stat = f"/proc/{pid}/stat"
    if os.path.exists(stat):
        with open(stat, encoding="utf-8") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"  # a zombie is already dead
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_stop_kills_the_whole_command_tree_not_just_the_shell(make_state, tmp_path):
    """Regression: on Linux, stopping killed only the shell; its child kept running and the call hung."""
    (tmp_path / "sleeper.py").write_text(
        "import os, time, pathlib\n"
        "pathlib.Path('child.pid').write_text(str(os.getpid()))\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    state, _ = make_state([])
    finished = threading.Event()

    def run():
        tool_run_command(state, "python sleeper.py", timeout_seconds=60)
        finished.set()

    worker = threading.Thread(target=run, daemon=True)
    started = time.monotonic()
    worker.start()

    pid_file = tmp_path / "child.pid"
    deadline = started + 15
    while not (pid_file.exists() and pid_file.read_text(encoding="utf-8").strip()) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert pid_file.exists(), "the command never started"
    child_pid = int(pid_file.read_text(encoding="utf-8"))

    kill_active_command(state)
    assert finished.wait(timeout=10), "run_command did not return after the kill"
    assert time.monotonic() - started < 25

    deadline = time.monotonic() + 5
    while _pid_alive(child_pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _pid_alive(child_pid), "the child process is still running after Stop"


def test_a_command_that_prints_a_lot_is_not_mistaken_for_a_hang(make_state):
    """Regression: output past the pipe buffer (about 4 KB on Windows, e.g. a failing test run's tracebacks)
    used to block the child on write until the timeout, and was then reported as a hang."""
    state, _ = make_state([])
    started = time.monotonic()
    out = tool_run_command(state, "python -c \"print('x' * 200000)\"", timeout_seconds=30)
    assert "exit_code: 0" in out and "timed out" not in out
    assert time.monotonic() - started < 20


def test_a_real_hang_still_times_out(make_state):
    state, _ = make_state([])
    out = tool_run_command(state, 'python -c "import time; time.sleep(30)"', timeout_seconds=1)
    assert "timed out after 1s" in out


def test_file_tools_refuse_content_with_nul_characters(make_state, tmp_path):
    """Regression: a mangled unicode escape reached disk as a NUL, and the test file could not be compiled."""
    from relay.tools.filesystem import tool_str_replace, tool_write_file

    state, _ = make_state([])
    nul = chr(0)
    out = tool_write_file(state, "bad.py", f"x = 'Caf{nul}e9'\n")
    assert out.startswith("Error:") and "NUL" in out
    assert not (tmp_path / "bad.py").exists()

    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    out = tool_str_replace(state, "ok.py", "x = 1", f"x = '{nul}'")
    assert out.startswith("Error:") and "NUL" in out
    assert (tmp_path / "ok.py").read_text(encoding="utf-8") == "x = 1\n"

    # a real backslash-u escape in source code is fine
    assert tool_write_file(state, "good.py", "x = 'Caf\\u00e9'\n").startswith("Wrote")
