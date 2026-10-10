"""`python -m evals matrix`: option parsing, the menu, orchestration, retries."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import evals.__main__ as cli
import evals.matrix as matrix
from evals.execute import RETRY_BACKOFF_S, run_with_retries
from evals.fake import ScriptedClient, call, say
from evals.matrix import (
    LOADED,
    Plan,
    default_targets,
    interactive_plan,
    load_defaults,
    parse_targets,
    plan_from_args,
    run_matrix,
)
from evals.tasks import load_tasks
from lm_studio_chat.providers.base import LLMProvider

DEFAULTS = {
    "repeats": 3,
    "timeout": 180,
    "defaults": {"openai": ["gpt-a", "gpt-b"], "anthropic": ["claude-a"], "lm_studio": [LOADED], "unsloth": [LOADED]},
    "also_offered": {"openai": ["gpt-c"], "anthropic": ["claude-b"]},
}


def args(**kw):
    base = dict(providers=None, models=None, repeats=None, tasks=None, timeout=None, judge=False,
                judge_provider=None, judge_model=None, verbose=False, dry_run=False, no_menu=False, out=None)
    base.update(kw)
    return NS(**base)


# ---- parsing ---------------------------------------------------------------------------------


def test_parse_targets_handles_pairs_loaded_models_and_colons_in_ids():
    assert parse_targets(["openai:gpt-a", "lm_studio", "lm_studio:loaded", "unsloth:llama3:8b"]) == [
        ("openai", "gpt-a"), ("lm_studio", None), ("unsloth", "llama3:8b"),
    ]


def test_parse_targets_rejects_unknown_providers():
    with pytest.raises(ValueError, match="unknown provider 'gemini'"):
        parse_targets(["gemini:pro"])


def test_providers_flag_expands_to_each_providers_default_models():
    plan = plan_from_args(args(providers="openai,anthropic"), DEFAULTS)
    assert plan.targets == [("openai", "gpt-a"), ("openai", "gpt-b"), ("anthropic", "claude-a")]
    assert plan.repeats == 3 and plan.timeout == 180 and plan.tasks is None


def test_models_and_providers_flags_combine_without_duplicates_and_options_override_defaults():
    plan = plan_from_args(args(models="anthropic:claude-b,openai:gpt-a", providers="openai", repeats=5, tasks="a,b", timeout=30), DEFAULTS)
    assert plan.targets == [("anthropic", "claude-b"), ("openai", "gpt-a"), ("openai", "gpt-b")]
    assert (plan.repeats, plan.timeout, plan.tasks) == (5, 30, ["a", "b"])


def test_no_options_means_no_plan_so_the_menu_can_ask():
    assert plan_from_args(args(), DEFAULTS) is None


def test_local_providers_default_to_whichever_model_is_loaded():
    assert default_targets(["lm_studio"], DEFAULTS) == [("lm_studio", None)]


def test_google_models_parse_and_readiness_follows_its_own_key_variable(monkeypatch):
    assert parse_targets(["google:gemini-3.8-flash"]) == [("google", "gemini-3.8-flash")]
    monkeypatch.delenv("GOOGLE_AI_STUDIO_API_KEY", raising=False)
    ready, note = matrix.provider_status("google")
    assert not ready and "GOOGLE_AI_STUDIO_API_KEY" in note
    monkeypatch.setenv("GOOGLE_AI_STUDIO_API_KEY", "key-test")
    assert matrix.provider_status("google") == (True, "GOOGLE_AI_STUDIO_API_KEY found")


def test_shipped_defaults_file_is_valid_and_names_known_providers():
    defaults = load_defaults()
    assert set(defaults["defaults"]) <= set(matrix.PROVIDERS)
    assert defaults["repeats"] >= 1 and all(defaults["defaults"][p] for p in ("openai", "anthropic"))


# ---- the menu --------------------------------------------------------------------------------


def scripted_input(answers):
    answers = list(answers)
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return answers.pop(0)

    ask.asked = asked
    return ask


READY = {"openai": (True, "key found"), "anthropic": (True, "key found"), "google": (False, "no key"), "lm_studio": (False, "server not reachable"), "unsloth": (False, "server not reachable")}


def menu(answers, **kw):
    said = []
    ask = scripted_input(answers)
    plan = interactive_plan(
        DEFAULTS, ask=ask, say=said.append, status=lambda p: READY[p],
        list_models=lambda p: ["gpt-from-account"] if p == "openai" else [],
        available_tasks=["read_and_answer", "count_files"], **kw,
    )
    return plan, said, ask


def test_menu_enter_accepts_every_default():
    # providers, openai models, anthropic models, repeats, timeout, tasks, start
    plan, said, ask = menu(["", "", "", "", "", "", ""])
    assert plan.targets == [("openai", "gpt-a"), ("openai", "gpt-b"), ("anthropic", "claude-a")]
    assert (plan.repeats, plan.timeout, plan.tasks) == (3, 180, None)
    assert any("= 3 models" in line.replace("(s)", "s") or "3 model(s)" in line for line in said)


def test_menu_numbers_names_and_extra_models():
    plan, said, _ = menu(["1,2", "3,gpt-custom", "2", "5", "60", "read_and_answer,bogus", "y"])
    assert plan.targets == [("openai", "gpt-c"), ("openai", "gpt-custom"), ("anthropic", "claude-b")]
    assert (plan.repeats, plan.timeout, plan.tasks) == (5, 60.0, ["read_and_answer"])
    assert any("Ignoring unknown task(s): bogus" in line for line in said)


def test_menu_lists_models_found_on_the_account():
    _, said, _ = menu(["1", "", "", "", "", "n"])
    assert any("gpt-from-account" in line for line in said)


def test_menu_reasks_after_bad_input_and_shows_what_is_ready():
    plan, said, _ = menu(["9", "x", "2", "", "", "", "", "yes"])
    assert plan.targets == [("anthropic", "claude-a")]
    assert any("Didn't understand" in line for line in said)
    assert any("anthropic" in line and "ready" in line and "key found" in line for line in said)
    assert any("lm_studio" in line and "not ready" in line for line in said)


def test_menu_can_be_declined_at_the_end():
    plan, _, _ = menu(["1", "", "", "", "", "n"])
    assert plan is None


def test_menu_reasks_for_bad_numbers():
    plan, said, _ = menu(["1", "", "zero", "-4", "2", "", "", ""])
    assert plan.repeats == 2 and sum("positive number" in line for line in said) == 2


# ---- running ---------------------------------------------------------------------------------


def fake_result(provider, model, rate=1.0):
    scores = {k: 1.0 for k in ("tool_selection", "args_valid", "outcome", "efficiency", "safety", "completed")}
    return {
        "meta": {"provider": provider, "model": model, "repeats": 1},
        "summary": {"tasks": 1, "runs": 3, "pass_rate": rate, "mean_scores": scores, "mean_duration_s": 2.0, "mean_nudges": 0.0},
        "tasks": {},
    }


def fake_run_model(calls):
    def run(provider, tasks, **kw):
        calls.append(provider.model_id)
        return fake_result(provider.id, provider.model_id), Path(f"{provider.model_id}.json"), Path(".")

    return run


def test_every_target_runs_and_a_comparison_file_is_saved(tmp_path):
    ran = []
    plan = Plan(targets=[("openai", "a"), ("anthropic", "b")], repeats=1)
    outcome = run_matrix(plan, out=tmp_path, verbose=False, make_provider=lambda p, m: NS(id=p, model_id=m, client=None),
                         run_model=fake_run_model(ran), say=lambda *_: None)
    assert ran == ["a", "b"] and outcome.exit_code == 0 and outcome.failures == []
    report = outcome.report_path.read_text(encoding="utf-8")
    assert "openai:a" in report and "anthropic:b" in report and "| Model |" in report


def test_a_model_that_cannot_be_reached_is_reported_and_the_rest_still_run(tmp_path):
    ran, said = [], []

    def make(provider, model):
        if model == "bad":
            raise RuntimeError("ANTHROPIC_API_KEY is required")
        return NS(id=provider, model_id=model, client=None)

    plan = Plan(targets=[("openai", "ok1"), ("anthropic", "bad"), ("openai", "ok2")], repeats=1)
    outcome = run_matrix(plan, out=tmp_path, verbose=False, make_provider=make, run_model=fake_run_model(ran), say=said.append)
    assert ran == ["ok1", "ok2"]
    assert outcome.failures == [("anthropic:bad", "RuntimeError: ANTHROPIC_API_KEY is required")] and outcome.exit_code == 1
    assert "## Not run" in outcome.report_path.read_text(encoding="utf-8")
    assert any("skipped: RuntimeError" in line for line in said)


def test_a_crash_inside_one_model_does_not_stop_the_others(tmp_path):
    def run_model(provider, tasks, **kw):
        if provider.model_id == "boom":
            raise ConnectionError("dropped")
        return fake_result(provider.id, provider.model_id), Path("x.json"), Path(".")

    plan = Plan(targets=[("openai", "boom"), ("openai", "fine")], repeats=1)
    outcome = run_matrix(plan, out=tmp_path, verbose=False, make_provider=lambda p, m: NS(id=p, model_id=m, client=None),
                         run_model=run_model, say=lambda *_: None)
    assert [r["meta"]["model"] for r in outcome.results] == ["fine"]
    assert outcome.failures[0][0] == "openai:boom" and outcome.exit_code == 1


def test_ctrl_c_keeps_finished_models_and_still_writes_the_comparison(tmp_path):
    def make(provider, model):
        if model == "second":
            raise KeyboardInterrupt
        return NS(id=provider, model_id=model, client=None)

    plan = Plan(targets=[("openai", "first"), ("openai", "second"), ("openai", "third")], repeats=1)
    ran = []
    outcome = run_matrix(plan, out=tmp_path, verbose=False, make_provider=make, run_model=fake_run_model(ran), say=lambda *_: None)
    assert ran == ["first"] and outcome.interrupted and outcome.exit_code == 130
    assert outcome.report_path and "openai:first" in outcome.report_path.read_text(encoding="utf-8")


def test_nothing_finishing_is_reported_plainly(tmp_path):
    said = []
    outcome = run_matrix(Plan(targets=[("openai", "x")]), out=tmp_path, verbose=False,
                         make_provider=lambda p, m: (_ for _ in ()).throw(RuntimeError("no key")), say=said.append)
    assert outcome.report_path is None and outcome.exit_code == 1
    assert any("nothing to compare" in line for line in said)


def scripted_provider(model_id):
    script = [call("read_file", path="notes.txt"), say("The deploy window is Thursday 02:00 UTC.")]
    return LLMProvider(id="scripted", label="s", client=ScriptedClient(script), model_id=model_id, base_url="",  # type: ignore[arg-type]
                       stream_usage=False, local=True)


def test_end_to_end_with_real_runner_and_two_scripted_models(tmp_path):
    plan = Plan(targets=[("openai", "model-a"), ("anthropic", "model-b")], repeats=1, tasks=["read_and_answer"])
    outcome = run_matrix(plan, out=tmp_path, verbose=False, make_provider=lambda p, m: scripted_provider(m),
                         sleep=lambda _s: None, say=lambda *_: None)
    assert outcome.exit_code == 0 and len(outcome.results) == 2
    assert all(r["summary"]["pass_rate"] == 1.0 for r in outcome.results)
    assert len(list(outcome.run_dir.glob("scripted__model-*.json"))) == 2  # both models land in this run's own folder
    assert outcome.run_dir.parent == tmp_path / "runs" and (outcome.run_dir / "dashboard.html").exists()
    assert (tmp_path / "index.html").exists()
    assert outcome.report_path.exists()


# ---- retries ---------------------------------------------------------------------------------


class FlakyClient(ScriptedClient):
    """Fails like a rate-limited API for the first ``fail_calls`` requests, then behaves."""

    def __init__(self, script, error_name, fail_calls, message="slow down"):
        super().__init__(script)
        self._left = fail_calls
        self._message = message
        self._error = type(error_name, (Exception,), {})

    def _create(self, **kwargs):
        if self._left > 0:
            self._left -= 1
            raise self._error(self._message)
        return super()._create(**kwargs)


def flaky_provider(error_name, fail_calls=4):  # the engine tries 4 parameter variants per request
    script = [call("read_file", path="notes.txt"), say("Thursday 02:00 UTC")]
    return LLMProvider(id="s", label="s", client=FlakyClient(script, error_name, fail_calls), model_id="m", base_url="",  # type: ignore[arg-type]
                       stream_usage=False, local=True)


def test_a_rate_limit_is_retried_after_a_pause_and_then_succeeds(tmp_path):
    task = next(t for t in load_tasks() if t["id"] == "read_and_answer")
    sleeps = []
    record = run_with_retries(task, flaky_provider("RateLimitError"), repeat=0, judge=None, timeout_s=30,
                              trace_dir=tmp_path, sleep=sleeps.append, say=lambda *_: None)
    assert record.passed and record.extra["retries"] == 1 and sleeps == [RETRY_BACKOFF_S[0]]


def test_real_failures_are_not_retried(tmp_path):
    task = next(t for t in load_tasks() if t["id"] == "read_and_answer")
    sleeps = []
    record = run_with_retries(task, flaky_provider("ValueError"), repeat=0, judge=None, timeout_s=30,
                              trace_dir=tmp_path, sleep=sleeps.append, say=lambda *_: None)
    assert not record.passed and record.extra["retries"] == 0 and sleeps == []


def test_retries_give_up_after_the_backoff_schedule(tmp_path):
    task = next(t for t in load_tasks() if t["id"] == "read_and_answer")
    sleeps = []
    record = run_with_retries(task, flaky_provider("APIConnectionError", fail_calls=10_000), repeat=0, judge=None,
                              timeout_s=30, trace_dir=tmp_path, sleep=sleeps.append, say=lambda *_: None)
    assert not record.passed and sleeps == list(RETRY_BACKOFF_S) and record.extra["retries"] == len(RETRY_BACKOFF_S)


# ---- the command -----------------------------------------------------------------------------


def test_dry_run_prints_the_plan_and_never_touches_a_provider(capsys, monkeypatch):
    monkeypatch.setattr(cli, "_live_provider", lambda *a: pytest.fail("a provider was created"))
    code = cli.main(["matrix", "--models", "openai:gpt-a,anthropic:claude-a", "--repeats", "2", "--tasks", "read_and_answer", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0 and "2 model(s) x 1 task(s) x 2 repeat(s) = 4 runs" in out and "anthropic:claude-a" in out


def test_unknown_provider_is_a_clear_error(capsys):
    assert cli.main(["matrix", "--models", "gemini:pro", "--dry-run"]) == 2
    assert "unknown provider 'gemini'" in capsys.readouterr().out


def test_with_no_options_and_no_terminal_it_runs_the_ready_providers_defaults(capsys, monkeypatch):
    monkeypatch.setattr(matrix, "provider_status", lambda p: (p == "anthropic", "x"))
    assert cli.main(["matrix", "--no-menu", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "anthropic:claude-haiku-5-5" in out and "openai:" not in out


def test_nothing_ready_says_what_to_do(capsys, monkeypatch):
    monkeypatch.setattr(matrix, "provider_status", lambda p: (False, "x"))
    assert cli.main(["matrix", "--no-menu"]) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().out


def test_the_menu_is_used_when_no_options_are_given(capsys, monkeypatch):
    monkeypatch.setattr(matrix, "provider_status", lambda p: (p == "openai", "key found"))
    monkeypatch.setattr(matrix, "remote_models", lambda p, timeout=5.0: [])
    code = matrix.cmd_matrix(args(dry_run=True), ask=scripted_input(["", "", "2", "", "", ""]), interactive=True)
    out = capsys.readouterr().out
    assert code == 0 and "Eval matrix: pick what to run" in out and "= 12 runs" not in out and "x 2 repeat(s)" in out


# ---- fail fast: don't keep calling a route that can't work ------------------------------------

from evals.execute import ModelUnavailable, classify_error, run_model  # noqa: E402

MODEL_403 = "PermissionDeniedError: Error code: 403 - {'error': {'message': 'Project `proj_x` does not have access to model `gpt-5-mini`', 'code': 'model_not_found'}}"
WORKSPACE_400 = "BadRequestError: Error code: 400 - This API key is not scoped to a workspace, so this request must include the anthropic-workspace-id header with the ID of the workspace"


@pytest.mark.parametrize(
    "error, expected_scope",
    [
        (MODEL_403, "model"),
        (WORKSPACE_400, "provider"),
        ("AuthenticationError: Error code: 401 - Incorrect API key provided", "provider"),
        ("RateLimitError: You exceeded your current quota (insufficient_quota)", "provider"),
        ("PermissionDeniedError: Error code: 403 - key not allowed from this region", "provider"),
        ("NotFoundError: Error code: 404 - model 'foo' not found", "model"),
        ("BadRequestError: Error code: 400 - unsupported parameter 'temperature'", "model"),
    ],
)
def test_permanent_errors_are_classified_by_what_they_poison(error, expected_scope):
    assert classify_error(error)[0] == expected_scope


@pytest.mark.parametrize("error", [None, "", "RateLimitError: slow down", "APIConnectionError: Connection error.", "ValueError: boom", "ScriptExhausted: x"])
def test_ordinary_and_transient_errors_are_not_treated_as_permanent(error):
    assert classify_error(error) is None


def test_the_workspace_error_tells_you_exactly_what_to_set():
    assert "ANTHROPIC_WORKSPACE_ID" in classify_error(WORKSPACE_400)[1]


def failing_provider(error_name, message, fail_calls=10_000):
    script = [call("read_file", path="notes.txt"), say("Thursday 02:00 UTC")] * 5
    client = FlakyClient(script, error_name, fail_calls, message)
    return LLMProvider(id="p", label="p", client=client, model_id="m", base_url="", stream_usage=False, local=True)  # type: ignore[arg-type]


def test_a_model_the_key_cannot_use_is_tried_once_then_abandoned_with_no_result_file(tmp_path):
    said = []
    tasks = [t for t in load_tasks() if t["id"] in ("read_and_answer", "count_files")]
    with pytest.raises(ModelUnavailable) as caught:
        run_model(failing_provider("PermissionDeniedError", "does not have access to model"), tasks, repeats=3, timeout=30,
                  judge=None, out=tmp_path, sleep=lambda _s: None, say=said.append)
    assert caught.value.scope == "model" and "no access to this model" in caught.value.reason
    assert sum("run 1/3" in line or "run 2/3" in line or "run 3/3" in line for line in said) == 1  # exactly one attempt
    assert not list(tmp_path.glob("*.json"))  # nothing real was measured, so no misleading 0% result


def test_a_dead_server_is_given_up_on_after_two_runs_not_all_of_them(tmp_path):
    sleeps, said = [], []
    tasks = [t for t in load_tasks() if t["id"] in ("read_and_answer", "count_files", "create_script")]
    with pytest.raises(ModelUnavailable) as caught:
        run_model(failing_provider("APIConnectionError", "Connection error."), tasks, repeats=3, timeout=30, judge=None,
                  out=tmp_path, sleep=sleeps.append, say=said.append)
    assert caught.value.scope == "provider"
    attempts = sum(1 for line in said if line.strip().startswith("[FAIL]"))
    assert attempts == 2 and len(sleeps) == 2 * len(RETRY_BACKOFF_S)


class BreaksAfterOneRun(ScriptedClient):
    """Works for the first run (2 model calls), then every request is refused like a revoked model."""

    def __init__(self):
        super().__init__([call("read_file", path="notes.txt"), say("Thursday 02:00 UTC")])
        self._error = type("NotFoundError", (Exception,), {})

    def _create(self, **kwargs):
        if self.calls_made >= 2:
            raise self._error("model gone")
        return super()._create(**kwargs)


def test_finished_runs_are_kept_and_marked_incomplete_if_the_model_breaks_part_way(tmp_path):
    provider = LLMProvider(id="p", label="p", client=BreaksAfterOneRun(), model_id="m", base_url="", stream_usage=False, local=True)  # type: ignore[arg-type]
    tasks = [t for t in load_tasks() if t["id"] == "read_and_answer"]
    result, path, _ = run_model(provider, tasks, repeats=3, timeout=30, judge=None, out=tmp_path, sleep=lambda _s: None, say=lambda *_: None)
    assert path.exists() and "model gone" in result["meta"]["aborted"]
    runs = result["tasks"]["read_and_answer"]["runs"]
    assert len(runs) == 2 and runs[0]["passed"] and runs[1]["error"]


def test_a_provider_level_failure_skips_that_providers_remaining_models_but_not_other_providers(tmp_path):
    ran, said = [], []

    def run(provider, tasks, **kw):
        ran.append(provider.model_id)
        if provider.model_id == "a":
            raise ModelUnavailable("provider", "API key rejected")
        return fake_result(provider.id, provider.model_id), Path("x.json"), Path(".")

    plan = Plan(targets=[("anthropic", "a"), ("anthropic", "b"), ("openai", "c")], repeats=1)
    outcome = run_matrix(plan, out=tmp_path, verbose=False, make_provider=lambda p, m: NS(id=p, model_id=m, client=None),
                         run_model=run, say=said.append)
    assert ran == ["a", "c"]  # b was never called
    reasons = dict(outcome.failures)
    assert reasons["anthropic:a"] == "API key rejected" and "stopped earlier" in reasons["anthropic:b"]
    assert [r["meta"]["model"] for r in outcome.results] == ["c"]


def test_a_model_level_failure_does_not_skip_the_providers_other_models(tmp_path):
    ran = []

    def run(provider, tasks, **kw):
        ran.append(provider.model_id)
        if provider.model_id == "bad":
            raise ModelUnavailable("model", "model not found")
        return fake_result(provider.id, provider.model_id), Path("x.json"), Path(".")

    plan = Plan(targets=[("openai", "bad"), ("openai", "good")], repeats=1)
    outcome = run_matrix(plan, out=tmp_path, verbose=False, make_provider=lambda p, m: NS(id=p, model_id=m, client=None),
                         run_model=run, say=lambda *_: None)
    assert ran == ["bad", "good"] and [r["meta"]["model"] for r in outcome.results] == ["good"]


def test_permanent_errors_are_never_retried(tmp_path):
    task = next(t for t in load_tasks() if t["id"] == "read_and_answer")
    sleeps = []
    record = run_with_retries(task, failing_provider("RateLimitError", "insufficient_quota"), repeat=0, judge=None, timeout_s=30,
                              trace_dir=tmp_path, sleep=sleeps.append, say=lambda *_: None)
    assert sleeps == [] and record.extra["retries"] == 0
