"""Token usage and dollar cost: capturing it, pricing it, estimating it when it was never recorded."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from evals.cost import (
    annotate_result,
    cost_line,
    describe_usage,
    estimate_usage,
    finalize_usage,
    find_rates,
    format_tokens,
    format_usd,
    load_pricing,
    merge_usage,
    output_tokens,
    price_usage,
    summarize,
    usage_cost,
)
from evals.fake import call, say
from evals.report import build_result, render_markdown
from evals.runner import RunRecord
from relay.chat.usage import add_usage, empty_usage, read_usage
from tests.conftest import drive

PRICING = {
    "gpt-x": {"input": 2.0, "cached_input": 0.2, "output": 10.0},
    "gpt-x2": {"input": 2.0, "cached_input": 0.2, "output": 10.0},
    "claude-y": {"input": 1.0, "output": 5.0},
}
SCORES = {k: 1.0 for k in ("tool_selection", "args_valid", "outcome", "efficiency", "safety", "completed")}


def usage(prompt=0, completion=0, cached=0, total=None, **extra):
    return {**empty_usage(), "prompt_tokens": prompt, "completion_tokens": completion, "cached_tokens": cached,
            "total_tokens": prompt + completion if total is None else total, "calls": 1, "calls_with_usage": 1, **extra}


def priced(result):
    """Price a freshly built result from the test price list (build_result itself uses the shipped one)."""
    for task in result["tasks"].values():
        for run in task["runs"]:
            run["cost_usd"] = run["judge_cost_usd"] = None
    return annotate_result(result, pricing=PRICING)


def record(task="t", passed=True, run_usage=None, repeat=0, answer="a"):
    return RunRecord(task, repeat, passed, dict(SCORES), [], None, [], 1, answer, 1.0, usage=run_usage)


# ---- reading usage off the wire --------------------------------------------------------------


def test_read_usage_pulls_cached_and_reasoning_tokens_when_present():
    wire = NS(prompt_tokens=100, completion_tokens=40, total_tokens=140,
              prompt_tokens_details=NS(cached_tokens=64), completion_tokens_details=NS(reasoning_tokens=25))
    assert read_usage(wire) == {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140,
                                "cached_tokens": 64, "reasoning_tokens": 25}


def test_read_usage_tolerates_providers_that_leave_fields_out():
    assert read_usage(NS(prompt_tokens=7, completion_tokens=3))["total_tokens"] == 10
    assert read_usage(NS(prompt_tokens=None, completion_tokens=None, total_tokens=None))["prompt_tokens"] == 0
    assert read_usage(NS(prompt_tokens=5, prompt_tokens_details={"cached_tokens": 2}))["cached_tokens"] == 2


# ---- the engine sums every round, not just the last -------------------------------------------


def test_the_engine_reports_usage_summed_over_every_model_call(make_state, tmp_path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    state, client = make_state([call("list_dir", path="."), call("read_file", path="a.txt"), say("done")])
    final, _ = drive(state)
    assert client.calls_made == 3
    # the scripted client reports prompt_tokens = 10 x call number, completion_tokens = 5
    assert final.usage["prompt_tokens"] == 10 + 20 + 30
    assert final.usage["completion_tokens"] == 15
    assert final.usage["calls"] == 3 and final.usage["calls_with_usage"] == 3


def test_a_model_that_reports_no_usage_is_counted_as_a_call_without_usage(make_state, monkeypatch):
    import evals.fake as fake

    monkeypatch.setattr(fake, "_chunks_for", lambda step, n: (c for c in [fake._chunk(content="hi"), fake._chunk(finish="stop")]))
    state, _ = make_state([say("hi")])
    final, _ = drive(state)
    assert final.usage == {**empty_usage(), "calls": 1}


# ---- prices ----------------------------------------------------------------------------------


def test_prices_are_found_by_exact_id_or_without_a_date_suffix_and_never_by_looser_match():
    assert find_rates("gpt-x", PRICING) is PRICING["gpt-x"]
    assert find_rates("claude-y-20251001", PRICING) is PRICING["claude-y"]
    assert find_rates("models/gpt-x", PRICING) is PRICING["gpt-x"]  # Google style ids
    assert find_rates("gpt-x-pro", PRICING) is None  # a different (dearer) model must not borrow gpt-x's price
    assert find_rates(None, PRICING) is None


def test_the_shipped_price_list_loads_and_covers_the_default_models():
    pricing = load_pricing()
    defaults = json.loads((__import__("pathlib").Path("evals/matrix_defaults.json")).read_text(encoding="utf-8"))["defaults"]
    for provider in ("openai", "anthropic", "google"):
        for model in defaults[provider]:
            rates = find_rates(model, pricing)
            assert rates and rates["input"] > 0 and rates["output"] > 0, f"no price for {model}"


def test_cost_bills_cached_input_at_the_cached_rate():
    # 1000 prompt tokens, 400 served from cache, 100 out:  600 x $2 + 400 x $0.2 + 100 x $10  per million
    assert usage_cost(usage(1000, 100, cached=400), PRICING["gpt-x"]) == pytest.approx((600 * 2 + 400 * 0.2 + 100 * 10) / 1e6)
    # no cached rate listed: cached tokens cost the normal input rate
    assert usage_cost(usage(1000, 100, cached=400), PRICING["claude-y"]) == pytest.approx((1000 * 1 + 100 * 5) / 1e6)


def test_thinking_tokens_a_provider_leaves_out_of_completion_are_still_billed():
    u = usage(prompt=100, completion=20, total=400)  # 280 tokens unaccounted for in completion_tokens
    assert output_tokens(u) == 300
    assert usage_cost(u, {"input": 0.0, "output": 1_000_000.0}) == pytest.approx(300)


def test_local_models_are_free_and_unlisted_models_have_no_dollar_figure():
    assert price_usage("lm_studio", "anything", usage(5000, 500), PRICING) == 0.0
    assert price_usage("openai", "mystery-model", usage(5000, 500), PRICING) is None
    assert price_usage("openai", "gpt-x", usage(1_000_000, 0), PRICING) == pytest.approx(2.0)


# ---- estimating when usage was never recorded -------------------------------------------------


def test_an_estimate_resends_the_whole_conversation_on_every_round():
    msgs = [
        {"role": "user", "content": "x" * 400},  # 100 tokens + 4
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "function": {"name": "f", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "1", "content": "y" * 800},  # 200 tokens + 4
    ]
    est = estimate_usage(msgs, answer="z" * 40, overhead_tokens=1000)
    assert est["source"] == "estimated" and est["calls"] == 2
    # round 1 sees overhead + user; round 2 sees all of that plus the assistant call and the tool result
    first = 1000 + 104
    assert est["prompt_tokens"] > first * 2 and est["prompt_tokens"] > 1000 + 104 + 100
    assert est["completion_tokens"] > 10  # the call plus the 10-token answer


def test_finalize_keeps_reported_usage_and_estimates_only_when_there_is_none():
    reported = usage(50, 10)
    assert finalize_usage(reported, [], "")["source"] == "reported"
    partial = {**usage(50, 10), "calls": 3, "calls_with_usage": 1}
    assert finalize_usage(partial, [], "")["source"] == "partial"
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    est = finalize_usage({**empty_usage(), "calls": 1}, msgs, "the answer")
    assert est["source"] == "estimated" and est["prompt_tokens"] > 0
    assert finalize_usage(None, [], "")["source"] == "none"


def test_a_retried_run_is_billed_for_every_attempt():
    merged = merge_usage(usage(100, 10), usage(40, 5), None)
    assert (merged["prompt_tokens"], merged["completion_tokens"], merged["calls"]) == (140, 15, 2)
    assert merge_usage(None, None) is None
    assert merge_usage(usage(1, 1), {**usage(1, 1), "source": "estimated"})["source"] == "mixed"


# ---- results ---------------------------------------------------------------------------------


def test_build_result_prices_runs_per_task_and_overall():
    one_run = usage(1_000_000, 100_000, source="reported")  # $2.00 in + $1.00 out on gpt-x
    result = priced(build_result(
        [record("a", True, one_run), record("a", False, one_run), record("b", True, one_run)],
        {"provider": "openai", "model": "gpt-x"},
    ))
    task_a, overall = result["tasks"]["a"]["cost"], result["summary"]["cost"]
    assert task_a["total_usd"] == pytest.approx(6.0) and task_a["per_run_usd"] == pytest.approx(3.0)
    assert task_a["per_pass_usd"] == pytest.approx(6.0)  # one of the two runs passed
    assert overall["total_usd"] == pytest.approx(9.0) and overall["per_pass_usd"] == pytest.approx(4.5)
    assert overall["source"] == "reported" and overall["free"] is False


def test_a_saved_cost_survives_a_later_price_change():
    result = build_result([record("a", True, usage(1_000_000, 0))], {"provider": "openai", "model": "gpt-x"})
    result["tasks"]["a"]["runs"][0]["cost_usd"] = 1.23  # what it cost when it ran
    annotate_result(result, pricing=PRICING)  # today's price would say $2.00
    assert result["tasks"]["a"]["runs"][0]["cost_usd"] == 1.23


def test_local_results_are_free_and_unpriced_models_show_tokens_not_dollars():
    local = build_result([record("a", True, usage(5000, 500))], {"provider": "lm_studio", "model": "qwen"})
    assert local["summary"]["cost"]["free"] and local["summary"]["cost"]["total_usd"] == 0.0
    unlisted = build_result([record("a", True, usage(5000, 500))], {"provider": "openai", "model": "mystery"})
    cost = unlisted["summary"]["cost"]
    assert cost["total_usd"] is None and cost["prompt_tokens"] == 5000
    assert "no price" in cost_line(cost)


def test_the_comparison_table_shows_cost_and_marks_estimates():
    paid = priced(build_result([record("a", True, usage(1_000_000, 0, source="reported"))], {"provider": "openai", "model": "gpt-x"}))
    guess = priced(build_result([record("a", True, usage(1_000_000, 0, source="estimated"))], {"provider": "openai", "model": "gpt-x2"}))
    local = build_result([record("a", True, usage(10, 1))], {"provider": "lm_studio", "model": "m"})
    table = render_markdown([paid, guess, local])
    assert "$/run" in table and "$/pass" in table
    rows = {line.split("|")[1].strip(): line for line in table.splitlines()[2:]}
    assert "| $2.00 |" in rows["openai:gpt-x"]
    assert "| ~$2.00 |" in rows["openai:gpt-x2"]
    assert "free" in rows["lm_studio:m"]


def test_old_results_get_an_estimate_from_their_transcript_files(tmp_path):
    stem = "openai__gpt-x"
    trace_dir = tmp_path / "traces" / stem
    trace_dir.mkdir(parents=True)
    messages = [
        {"role": "user", "content": "read notes.txt"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "function": {"name": "read_file", "arguments": '{"path": "notes.txt"}'}}]},
        {"role": "tool", "tool_call_id": "1", "content": "Thursday 02:00 UTC"},
    ]
    (trace_dir / "t__0.json").write_text(json.dumps({"task": "t", "error": None, "messages": messages}), encoding="utf-8")
    old = {
        "meta": {"provider": "openai", "model": "gpt-x"},
        "summary": {},
        "tasks": {"t": {"runs": [{"task_id": "t", "repeat": 0, "passed": True, "answer": "Thursday", "usage": None}]}},
    }
    annotate_result(old, run_dir=tmp_path, stem=stem, pricing=PRICING)
    run = old["tasks"]["t"]["runs"][0]
    assert run["usage"]["source"] == "estimated" and run["usage"]["calls"] == 2
    assert run["cost_usd"] > 0 and old["summary"]["cost"]["source"] == "estimated"

    missing = {"meta": {"provider": "openai", "model": "gpt-x"}, "summary": {},
               "tasks": {"t": {"runs": [{"task_id": "t", "repeat": 0, "passed": True, "answer": ""}]}}}
    annotate_result(missing, run_dir=tmp_path / "elsewhere", stem=stem, pricing=PRICING)
    assert missing["tasks"]["t"]["runs"][0]["usage"] is None  # no transcript: say nothing rather than invent


def test_judge_cost_is_kept_apart_from_the_model_under_test():
    run = record("a", True, usage(1_000_000, 0))
    run.judge = {"status": "scored", "score": 5, "model": "claude-y", "usage": usage(1_000_000, 0)}
    cost = priced(build_result([run], {"provider": "openai", "model": "gpt-x"}))["summary"]["cost"]
    assert cost["total_usd"] == pytest.approx(2.0) and cost["judge_usd"] == pytest.approx(1.0)


def test_formatting():
    assert format_usd(0.00312) == "$0.0031" and format_usd(0.4821) == "$0.482" and format_usd(12.3) == "$12.30"
    assert format_usd(None) == "n/a" and format_usd(0.0, free=True) == "free"
    assert format_tokens(850) == "850" and format_tokens(12_340) == "12.3k" and format_tokens(2_500_000) == "2.50M"
    assert "free" in describe_usage("lm_studio", "m", usage(100, 10))
    assert "no price" in describe_usage("openai", "mystery", usage(100, 10), PRICING)
    assert describe_usage("openai", "gpt-x", {**usage(1000, 100), "source": "estimated"}, PRICING).count("~") == 2
    assert summarize([])["total_usd"] is None
    assert add_usage(empty_usage(), usage(3, 4))["prompt_tokens"] == 3


# ---- wiring: runner, judge, dashboard ---------------------------------------------------------


def test_a_run_records_the_tokens_every_model_call_used():
    from evals.policies import POLICIES
    from evals.runner import run_task
    from evals.selfcheck import scripted_provider_factory
    from evals.tasks import load_tasks

    task = next(t for t in load_tasks() if t["id"] == "read_and_answer")
    rec = run_task(task, scripted_provider_factory(POLICIES["read_and_answer"]["good"]))
    u = rec.usage
    assert u["source"] == "reported" and u["calls"] == u["calls_with_usage"] == rec.model_calls
    n = u["calls"]
    assert u["prompt_tokens"] == 10 * n * (n + 1) // 2 and u["completion_tokens"] == 5 * n


def test_the_judge_reports_what_it_used_and_which_model_it_was():
    from evals.judge import LLMJudge

    reply = NS(choices=[NS(message=NS(content='{"score": 4, "reasoning": "ok"}'))],
               usage=NS(prompt_tokens=900, completion_tokens=30, total_tokens=930))
    client = NS(chat=NS(completions=NS(create=lambda **_: reply)))
    out = LLMJudge(client, "judge-model").grade({"prompt": "p", "expect": {"rubric": {"criteria": "c"}}}, "a", "s")
    assert out["score"] == 4 and out["model"] == "judge-model"
    assert out["usage"]["prompt_tokens"] == 900 and out["usage"]["completion_tokens"] == 30


def test_the_dashboard_summaries_carry_cost(tmp_path):
    from evals.dashboard import model_summary, run_summary

    result = priced(build_result([record("a", True, usage(1_000_000, 0, source="reported"))], {"provider": "openai", "model": "gpt-x"}))
    m = model_summary(result)
    assert m["cost_usd"] == pytest.approx(2.0) and m["cost_per_pass"] == pytest.approx(2.0)
    assert m["cost_source"] == "reported" and m["free"] is False

    run_dir = tmp_path / "runs" / "20261009-150237"
    run_dir.mkdir(parents=True)
    (run_dir / "openai__gpt-x.json").write_text(json.dumps(result), encoding="utf-8")
    (run_dir / "lm_studio__q.json").write_text(
        json.dumps(build_result([record("a", True, usage(5, 5))], {"provider": "lm_studio", "model": "q", "timestamp": "2"})), encoding="utf-8")
    summary = run_summary(run_dir)
    assert summary["cost_usd"] == pytest.approx(2.0)  # the local model adds nothing
    assert summary["cost_estimated"] is False and summary["cost_unpriced"] == 0


def test_report_expands_globs_and_skips_the_run_manifest(tmp_path, capsys):
    import evals.__main__ as cli

    for model in ("a", "b"):
        (tmp_path / f"openai__{model}.json").write_text(
            json.dumps(build_result([record("t", True, usage(10, 1))], {"provider": "openai", "model": model})), encoding="utf-8")
    (tmp_path / "run.json").write_text(json.dumps({"id": "x", "status": "complete", "tasks": ["t"], "targets": ["openai:a"]}), encoding="utf-8")
    assert cli.main(["report", str(tmp_path / "*.json")]) == 0
    out = capsys.readouterr().out
    assert "openai:a" in out and "openai:b" in out
    assert cli.main(["report", str(tmp_path / "run.json")]) == 1  # nothing usable: say so instead of crashing


def test_run_with_several_providers_points_at_matrix(capsys):
    import evals.__main__ as cli

    with pytest.raises(SystemExit):
        cli.main(["run", "--provider", "openai,anthropic"])
    assert "matrix --providers openai,anthropic" in capsys.readouterr().err
