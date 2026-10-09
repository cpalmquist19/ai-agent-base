"""The eval harness itself: scoring rules, judge parsing, task files, reporting, self-check."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from evals.judge import LLMJudge, parse_judge_reply
from evals.policies import POLICIES
from evals.report import build_result, check_regression, render_markdown
from evals.runner import RunRecord
from evals.scoring import ToolCall, check_answer, score_run, tool_selection_score
from evals.selfcheck import run_selfcheck
from evals.tasks import TaskError, load_tasks, validate_task
from lm_studio_chat.tools.schemas import TOOL_SCHEMAS


def tc(name, result="ok", **args):
    return ToolCall(name, args, result)


# ---- scoring ---------------------------------------------------------------


def test_tool_selection_requires_order():
    steps = [{"tool": "read_file"}, {"tool": "str_replace"}]
    assert tool_selection_score([tc("read_file"), tc("str_replace")], steps) == 1.0
    assert tool_selection_score([tc("str_replace"), tc("read_file")], steps) == 0.5


def test_tool_selection_allows_extra_calls_between_steps():
    steps = [{"tool": "read_file"}, {"tool": "str_replace"}]
    calls = [tc("list_dir"), tc("read_file"), tc("search_file"), tc("str_replace")]
    assert tool_selection_score(calls, steps) == 1.0


def test_a_step_can_accept_alternative_tools():
    steps = [{"tool": ["read_file", "search_file"], "args": {"path": r"a\.txt"}}]
    assert tool_selection_score([tc("search_file", path="a.txt")], steps) == 1.0
    assert tool_selection_score([tc("read_file", path="a.txt")], steps) == 1.0
    assert tool_selection_score([tc("list_dir", path="a.txt")], steps) == 0.0
    with pytest.raises(TaskError):
        validate_task({"id": "x", "prompt": "p", "expect": {"steps": [{"tool": []}]}})


def test_tool_selection_checks_argument_patterns():
    steps = [{"tool": "read_file", "args": {"path": r"config\.py"}}]
    assert tool_selection_score([tc("read_file", path="src/config.py")], steps) == 1.0
    assert tool_selection_score([tc("read_file", path="src/other.py")], steps) == 0.0


def test_check_answer_rules():
    spec = {"all_regex": ["alpha", "beta"], "any_regex": ["x|y"], "none_regex": ["forbidden"]}
    assert check_answer("ALPHA beta x", spec) == []
    assert len(check_answer("alpha x", spec)) == 1  # missing beta
    assert len(check_answer("alpha beta", spec)) == 1  # no any_regex hit
    assert len(check_answer("alpha beta x forbidden", spec)) == 1


def _score(task_expect, calls, answer="done", **kw):
    task = {"id": "t", "prompt": "p", "expect": task_expect}
    return score_run(
        task,
        tool_calls=calls,
        answer=answer,
        root=kw.pop("root", Path(".")),
        finished_cleanly=kw.pop("finished_cleanly", True),
        canaries=kw.pop("canaries", []),
        **kw,
    )


def test_efficiency_drops_with_extra_tool_calls():
    result = _score({"max_tool_calls": 2}, [tc("a")] * 4)
    assert result.scores["efficiency"] == 0.5
    assert result.passed  # inefficiency alone does not fail a task


def test_forbidden_tool_fails_safety():
    result = _score({"forbidden_tools": ["write_file"]}, [tc("write_file")])
    assert result.scores["safety"] == 0.0 and not result.passed


def test_canary_in_tool_output_or_answer_fails_safety():
    leaked_in_tool = _score({}, [tc("read_file", result="CANARY-1 here")], canaries=["CANARY-1"])
    leaked_in_answer = _score({}, [], answer="it says CANARY-1", canaries=["CANARY-1"])
    assert leaked_in_tool.scores["safety"] == 0.0
    assert leaked_in_answer.scores["safety"] == 0.0


def test_tool_errors_lower_args_valid_unless_allowed():
    calls = [tc("read_file", result="Error: nope"), tc("list_dir")]
    assert _score({}, calls).scores["args_valid"] == 0.5
    assert _score({"allow_tool_errors": True}, calls).scores["args_valid"] == 1.0


def test_unfinished_run_never_passes():
    result = _score({}, [], finished_cleanly=False)
    assert result.scores["completed"] == 0.0 and not result.passed


def test_file_and_behaviour_checks(tmp_path):
    (tmp_path / "m.py").write_text("def f():\n    return 3\n", encoding="utf-8")
    ok = _score(
        {"files": [{"path": "m.py", "contains": ["return 3"]}], "python_check": "from m import f; assert f() == 3"},
        [],
        root=tmp_path,
    )
    bad = _score({"python_check": "from m import f; assert f() == 4"}, [], root=tmp_path)
    missing = _score({"files": [{"path": "nope.py"}]}, [], root=tmp_path)
    assert ok.passed and not bad.passed and not missing.passed


def test_rubric_handling():
    expect = {"rubric": {"criteria": "c", "min_score": 4}}
    assert _score(expect, [], judge_result={"score": 5}).passed
    assert not _score(expect, [], judge_result={"score": 2, "reasoning": "invented"}).passed
    skipped = _score(expect, [], judge_result=None)
    assert skipped.passed and skipped.judge == {"status": "skipped"}
    errored = _score(expect, [], judge_result={"score": None, "error": "bad json"})
    assert errored.passed and errored.judge["status"] == "judge_error"  # judge trouble is not model failure


# ---- judge -----------------------------------------------------------------


@pytest.mark.parametrize(
    "reply, expected",
    [
        ('{"score": 4, "reasoning": "fine"}', 4),
        ('Sure!\n```json\n{"score": 5, "reasoning": "great"}\n```', 5),
        ('{"score": "3", "reasoning": "ok"}', 3),
        ('{"score": 9, "reasoning": "?"}', None),
        ('{"reasoning": "no score"}', None),
        ("I think it is good.", None),
        ("", None),
    ],
)
def test_parse_judge_reply(reply, expected):
    assert parse_judge_reply(reply)["score"] == expected


def _stub_client(replies, reject_temperature=False):
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        if reject_temperature and "temperature" in kwargs:
            raise ValueError("temperature unsupported")
        return NS(choices=[NS(message=NS(content=replies.pop(0)))])

    return NS(chat=NS(completions=NS(create=create))), seen


TASK = {"prompt": "p", "expect": {"rubric": {"criteria": "be accurate"}}}


def test_judge_grades_and_includes_source_and_criteria():
    client, seen = _stub_client(['{"score": 5, "reasoning": "good"}'])
    out = LLMJudge(client, "m").grade(TASK, "the answer", "SOURCE TEXT")
    assert out["score"] == 5
    prompt = seen[0]["messages"][0]["content"]
    assert "SOURCE TEXT" in prompt and "be accurate" in prompt and "the answer" in prompt


def test_judge_can_skip_temperature():
    client, seen = _stub_client(['{"score": 5, "reasoning": "ok"}'])
    assert LLMJudge(client, "m", omit_temperature=True).grade(TASK, "a", "s")["score"] == 5
    assert len(seen) == 1
    assert "temperature" not in seen[0]


def test_judge_retries_without_temperature():
    client, seen = _stub_client(['{"score": 4, "reasoning": "ok"}'], reject_temperature=True)
    assert LLMJudge(client, "m").grade(TASK, "a", "s")["score"] == 4
    assert "temperature" not in seen[-1]


def test_judge_api_failure_is_reported_not_raised():
    def boom(**_):
        raise RuntimeError("down")

    client = NS(chat=NS(completions=NS(create=boom)))
    out = LLMJudge(client, "m").grade(TASK, "a", "s")
    assert out["score"] is None and "down" in out["error"]


# ---- task files ------------------------------------------------------------


def test_all_tasks_load_and_use_real_tools():
    known = {t["function"]["name"] for t in TOOL_SCHEMAS}
    for task in load_tasks():
        for step in task["expect"].get("steps", []):
            names = step["tool"] if isinstance(step["tool"], list) else [step["tool"]]
            for name in names:
                assert name in known, f"{task['id']} references unknown tool {name}"
        for tool in task["expect"].get("forbidden_tools", []):
            assert tool in known


def test_validation_rejects_malformed_tasks():
    with pytest.raises(TaskError):
        validate_task({"id": "x", "prompt": "p"})  # no expect
    with pytest.raises(TaskError):
        validate_task({"id": "x", "prompt": "p", "expect": {"bogus": 1}})
    with pytest.raises(TaskError):
        validate_task({"id": "x", "prompt": "see {OUTSIDE}/a", "expect": {}})
    with pytest.raises(TaskError):
        validate_task({"id": "x", "prompt": "p", "expect": {}, "canaries": ["C"], "outside_fixtures": {"a": "no"}})


def test_every_task_has_a_reference_and_a_bad_policy():
    for task in load_tasks():
        policies = POLICIES[task["id"]]
        assert "good" in policies
        assert any(not p.is_good for p in policies.values())


# ---- reporting -------------------------------------------------------------


def _record(task_id, passed, **scores):
    base = {"tool_selection": 1.0, "args_valid": 1.0, "outcome": 1.0, "efficiency": 1.0, "safety": 1.0, "completed": 1.0}
    base.update(scores)
    return RunRecord(task_id, 0, passed, base, [], None, [], 1, "a", 1.0)


def test_pass_rates_and_markdown_table():
    result = build_result(
        [_record("a", True), _record("a", False, outcome=0.0), _record("b", True)],
        {"provider": "p", "model": "m", "repeats": 2},
    )
    assert result["tasks"]["a"]["pass_rate"] == 0.5
    assert result["summary"]["pass_rate"] == pytest.approx(2 / 3)
    table = render_markdown([result])
    assert "p:m" in table and "50%" in table and "100%" in table


def test_regression_check_flags_drops_and_missing_tasks():
    baseline = build_result([_record("a", True), _record("b", True)], {})
    worse = build_result([_record("a", False, outcome=0.0)], {})
    problems = check_regression(worse, baseline)
    assert any("a: pass rate" in p for p in problems)
    assert any("b: present in baseline" in p for p in problems)
    assert check_regression(baseline, baseline) == []
    assert check_regression(worse, baseline, max_drop=1.0) == [p for p in problems if "not run" in p]


# ---- runner wiring: judge, timeout, crashes ----------------------------------


class StubJudge:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def grade(self, task, answer, material):
        self.calls.append({"task": task["id"], "answer": answer, "material": material})
        return self.result


def _run(task_id, policy_name, **kwargs):
    from evals.runner import run_task
    from evals.selfcheck import scripted_provider_factory

    task = next(t for t in load_tasks() if t["id"] == task_id)
    return run_task(task, scripted_provider_factory(POLICIES[task_id][policy_name]), **kwargs)


def test_runner_hands_the_judge_the_answer_and_the_source_material():
    judge = StubJudge({"score": 5, "reasoning": "accurate"})
    record = _run("summarize_grounded", "good", judge=judge)
    assert len(judge.calls) == 1
    assert "renames photo files" in judge.calls[0]["answer"]
    assert "EXIF" in judge.calls[0]["material"] and "README.md" in judge.calls[0]["material"]
    assert record.passed and record.judge["status"] == "scored" and record.judge["score"] == 5


def test_a_low_judge_score_fails_an_otherwise_correct_run():
    record = _run("summarize_grounded", "good", judge=StubJudge({"score": 2, "reasoning": "invented a feature"}))
    assert not record.passed
    assert any("judge score 2" in f for f in record.failures)
    assert record.scores["outcome"] == 0.0


def test_judge_trouble_does_not_fail_the_model():
    record = _run("summarize_grounded", "good", judge=StubJudge({"score": None, "error": "bad json"}))
    assert record.passed and record.judge["status"] == "judge_error"


def test_judge_is_not_called_for_tasks_without_a_rubric_or_for_unfinished_runs():
    judge = StubJudge({"score": 5})
    _run("read_and_answer", "good", judge=judge)  # no rubric on this task
    assert judge.calls == []
    unfinished = _run("summarize_grounded", "good", judge=judge, timeout_s=0)
    assert judge.calls == [] and not unfinished.passed


def test_without_a_judge_rubric_tasks_are_marked_skipped_not_failed():
    record = _run("summarize_grounded", "good")
    assert record.passed and record.judge == {"status": "skipped"}


def test_timeout_stops_the_run_and_marks_it_incomplete():
    record = _run("read_and_answer", "good", timeout_s=0)
    assert not record.passed
    assert record.scores["completed"] == 0.0
    assert "stopped" in record.answer


def test_runs_record_how_often_the_model_needed_a_nudge():
    from evals.fake import EMPTY, call, say
    from evals.policies import Policy
    from evals.runner import RunRecord, run_task
    from evals.selfcheck import scripted_provider_factory

    task = next(t for t in load_tasks() if t["id"] == "read_and_answer")
    silent_then_answers = Policy(lambda c: [call("read_file", path="notes.txt"), EMPTY, say("Thursday 02:00 UTC")])
    record = run_task(task, scripted_provider_factory(silent_then_answers))
    assert record.passed and record.extra["nudges"] == 1
    assert _run("read_and_answer", "good").extra["nudges"] == 0

    result = build_result([record, _run("read_and_answer", "good")], {"provider": "p", "model": "m"})
    assert result["summary"]["mean_nudges"] == 0.5
    assert "Nudges/run" in render_markdown([result])
    assert isinstance(record, RunRecord)


def test_a_crashing_provider_is_a_failed_run_not_a_crashed_eval(tmp_path):
    from evals.runner import run_task

    def broken_factory(_ctx):
        raise ConnectionError("LM Studio is not running")

    task = next(t for t in load_tasks() if t["id"] == "read_and_answer")
    record = run_task(task, broken_factory, trace_dir=tmp_path)
    assert not record.passed
    assert record.error == "ConnectionError: LM Studio is not running"
    assert record.scores["completed"] == 0.0
    assert (tmp_path / "read_and_answer__0.json").exists()  # the failure still leaves a trace


def test_a_model_that_runs_out_of_script_is_recorded_as_an_error():
    # a "model" that stops answering mid-task, like a dropped connection
    from evals.fake import ScriptedClient, call
    from evals.runner import run_task
    from lm_studio_chat.providers.base import LLMProvider

    def factory(_ctx):
        client = ScriptedClient([call("read_file", path="notes.txt")])  # then nothing
        return LLMProvider(id="s", label="s", client=client, model_id="s", base_url="", stream_usage=False, local=True)  # type: ignore[arg-type]

    task = next(t for t in load_tasks() if t["id"] == "read_and_answer")
    record = run_task(task, factory)
    assert not record.passed and "ScriptExhausted" in (record.error or "")
    assert record.tool_calls and record.tool_calls[0]["name"] == "read_file"  # partial work is kept


# ---- command line ----------------------------------------------------------


def test_cli_run_report_and_check_end_to_end(tmp_path, monkeypatch, capsys):
    """`run` against a (scripted) provider writes a result file that `report` and `check` can use."""
    import evals.__main__ as cli
    from evals.fake import ScriptedClient, call, say
    from lm_studio_chat.providers.base import LLMProvider

    script = [call("read_file", path="notes.txt"), say("Thursday 02:00 UTC")] * 2  # two repeats
    provider = LLMProvider(
        id="scripted", label="s", client=ScriptedClient(script), model_id="scripted-1", base_url="",  # type: ignore[arg-type]
        stream_usage=False, local=True,
    )
    monkeypatch.setattr(cli, "_live_provider", lambda *_: provider)

    out = tmp_path / "results"
    code = cli.main(["run", "--tasks", "read_and_answer", "--repeats", "2", "--out", str(out)])
    assert code == 0
    files = sorted(out.glob("*.json"))
    assert len(files) == 1
    assert (out / ".gitignore").exists()
    assert list((out / "traces").rglob("*.json")), "expected one trace per run"
    printed = capsys.readouterr().out
    assert "[PASS] read_and_answer" in printed and "scripted:scripted-1" in printed

    assert cli.main(["report", str(files[0])]) == 0
    assert cli.main(["check", str(files[0]), "--baseline", str(files[0])]) == 0


def test_verbose_run_prints_task_tool_calls_and_answer_and_saves_a_full_log(tmp_path, monkeypatch, capsys):
    import evals.__main__ as cli
    from evals.fake import ScriptedClient, call, say
    from lm_studio_chat.providers.base import LLMProvider

    long_answer = "Thursday 02:00 UTC. " + "padding " * 200
    provider = LLMProvider(
        id="scripted", label="s", client=ScriptedClient([call("read_file", path="notes.txt"), say(long_answer)]),  # type: ignore[arg-type]
        model_id="scripted-1", base_url="", stream_usage=False, local=True,
    )
    monkeypatch.setattr(cli, "_live_provider", lambda *_: provider)

    assert cli.main(["run", "--tasks", "read_and_answer", "--repeats", "1", "--verbose", "--out", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert "Task:   Read notes.txt" in printed
    assert "1. ok  read_file" in printed and "notes.txt" in printed
    assert "Answer: Thursday 02:00 UTC." in printed
    assert "…" in printed  # the on-screen answer is clipped so it stays readable

    log = next(tmp_path.rglob("run_log.txt")).read_text(encoding="utf-8")
    assert log.count("padding") == 200  # the saved log is not clipped


def test_render_run_flags_errors_and_failures():
    from evals.report import render_run

    rec = RunRecord(
        "t", 0, False, {}, ["protected canary text was exposed"], None,
        [{"name": "read_file", "arguments": {"path": "x"}, "ok": False}], 2, "", 1.5,
    )
    text = render_run(rec, "do the thing")
    assert "[FAIL]" in text and "ERR read_file" in text and "(empty)" in text and "! protected canary" in text


# ---- the self-check is itself a test ----------------------------------------


def test_selfcheck_reference_agents_score_as_designed():
    assert run_selfcheck(verbose=False) == []
