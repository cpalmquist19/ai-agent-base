"""Run every task against one provider/model and save the result. Shared by ``run`` and ``matrix``."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from evals.cost import cost_line, describe_usage, find_rates, load_pricing, merge_usage
from evals.report import build_result, render_run, save_result, save_run_log
from evals.runner import RunRecord, run_task

# Errors that mean "the API had a bad moment", not "the model got it wrong". Retrying them keeps an
# unattended multi-model run from recording a rate limit as a failed task.
TRANSIENT_ERRORS = (
    "RateLimitError",
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "ServiceUnavailable",
    "Overloaded",
)
RETRY_BACKOFF_S = (5, 20)
# After this many runs in a row that still failed with transient errors despite retries, stop hammering.
MAX_CONSECUTIVE_UNREACHABLE = 2


class ModelUnavailable(Exception):
    """This model can't be run, and retrying won't change that.

    ``scope`` is ``"model"`` (try the provider's other models) or ``"provider"`` (the key, quota, workspace or
    server is the problem, so every model on that provider would fail the same way).
    """

    def __init__(self, scope: str, reason: str):
        super().__init__(reason)
        self.scope = scope
        self.reason = reason


def classify_error(error: str | None) -> tuple[str, str] | None:
    """(scope, reason) for an error that retrying cannot fix, or None if it may be transient or the model's own doing."""
    if not error:
        return None
    low = error.lower()
    short = " ".join(error.split())[:200]
    if "insufficient_quota" in low or "exceeded your current quota" in low:
        return "provider", f"quota exhausted ({short})"
    if "anthropic-workspace-id" in low or ("workspace" in low and "api key" in low):
        return "provider", (
            "this API key needs a workspace: set ANTHROPIC_WORKSPACE_ID in .env to the workspace ID "
            f"(Anthropic Console, Settings, Workspaces). API said: {short}"
        )
    if "AuthenticationError" in error or "invalid api key" in low or "incorrect api key" in low or "invalid x-api-key" in low:
        return "provider", f"API key rejected ({short})"
    if "PermissionDeniedError" in error:
        if "model" in low:
            return "model", f"no access to this model ({short})"
        return "provider", f"permission denied for this API key ({short})"
    if "NotFoundError" in error or "model_not_found" in low or ("model" in low and "does not exist" in low):
        return "model", f"model not found or not available ({short})"
    if "BadRequestError" in error or "UnprocessableEntityError" in error:
        return "model", f"the API rejected the request, likely an unsupported model or parameter ({short})"
    return None


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5, cwd=Path(__file__).parent
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def is_transient(record: RunRecord) -> bool:
    return bool(record.error) and any(name in record.error for name in TRANSIENT_ERRORS)


def run_with_retries(
    task: dict[str, Any],
    provider: Any,
    *,
    repeat: int,
    judge: Any,
    timeout_s: float,
    trace_dir: Path,
    sleep: Callable[[float], None] = time.sleep,
    say: Callable[[str], None] = print,
) -> RunRecord:
    record = run_task(task, lambda _ctx: provider, repeat=repeat, judge=judge, timeout_s=timeout_s, trace_dir=trace_dir)
    retries = 0
    discarded = []  # a retried attempt was still billed for whatever it got through
    # a permanent error (bad key, wrong model) is never retried; only "bad moment" errors are
    while is_transient(record) and not classify_error(record.error) and retries < len(RETRY_BACKOFF_S):
        discarded.append(record.usage)
        say(f"         transient API error ({record.error.split(':')[0]}); retrying in {RETRY_BACKOFF_S[retries]}s")
        sleep(RETRY_BACKOFF_S[retries])
        retries += 1
        record = run_task(task, lambda _ctx: provider, repeat=repeat, judge=judge, timeout_s=timeout_s, trace_dir=trace_dir)
    if discarded:
        record.usage = merge_usage(record.usage, *discarded)
    record.extra["retries"] = retries
    return record


def run_model(
    provider: Any,
    tasks: list[dict[str, Any]],
    *,
    repeats: int,
    timeout: float,
    judge: Any,
    out: Path,
    verbose: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    say: Callable[[str], None] = print,
) -> tuple[dict[str, Any], Path, Path]:
    """Run ``tasks`` x ``repeats`` on one provider. Returns (result, result file, trace dir).

    Stops early, without writing a result file, if the very first runs show the model can't be reached at all
    (raises ``ModelUnavailable``). If it breaks down part-way, the finished runs are saved and marked ``aborted``.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")  # when this model started; ``out`` is the run's own folder
    safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", provider.model_id)
    base = f"{provider.id}__{safe_model}"
    stem, n = base, 2
    while (out / f"{stem}.json").exists() or (out / "traces" / stem).exists():  # same model twice in one run
        stem, n = f"{base}-{n}", n + 1
    trace_dir = out / "traces" / stem

    say(f"Running {len(tasks)} task(s) x {repeats} on {provider.id}:{provider.model_id}")
    pricing = load_pricing()
    records: list[RunRecord] = []
    prompts: dict[str, str] = {}
    abort: tuple[str, str] | None = None
    unreachable_streak = 0
    for task in tasks:
        for repeat in range(repeats):
            rec = run_with_retries(
                task, provider, repeat=repeat, judge=judge, timeout_s=timeout, trace_dir=trace_dir, sleep=sleep, say=say
            )
            records.append(rec)
            prompts[task["id"]] = task["prompt"]
            spent = describe_usage(provider.id, provider.model_id, rec.usage, pricing)
            if verbose:
                say(render_run(rec, task["prompt"]))
                if spent:
                    say(f"  Tokens and cost: {spent}")
                say("")
            else:
                mark = "PASS" if rec.passed else "FAIL"
                say(f"  [{mark}] {task['id']:<28} run {repeat + 1}/{repeats}  {rec.duration_s:>6.1f}s  calls={len(rec.tool_calls):<3}  {spent}".rstrip())
                for failure in rec.failures:
                    say(f"         - {failure}")
            save_run_log(records, prompts, trace_dir)  # readable full log, refreshed after every run

            abort = classify_error(rec.error)
            if abort is None:
                unreachable_streak = unreachable_streak + 1 if is_transient(rec) else 0
                if unreachable_streak >= MAX_CONSECUTIVE_UNREACHABLE:
                    scope = "provider" if "APIConnectionError" in (rec.error or "") else "model"
                    abort = (scope, f"the API kept failing after retries ({' '.join((rec.error or '').split())[:160]})")
            if abort:
                break
        if abort:
            break

    if abort:
        scope, reason = abort
        say(f"  STOPPED: {reason}")
        say(f"  Not retrying: the remaining runs would fail the same way ({'skipping this provider too' if scope == 'provider' else 'this model only'}).")
        if all(r.error for r in records):  # nothing real was measured; don't write a misleading 0% result file
            raise ModelUnavailable(scope, reason)

    meta = {
        "provider": provider.id,
        "model": provider.model_id,
        "repeats": repeats,
        "timestamp": stamp,
        "git_sha": git_sha(),
        "judge": bool(judge),
        "price_per_1m": find_rates(provider.model_id, pricing),  # None: local, or no price listed
    }
    if abort:
        meta["aborted"] = abort[1]
    result = build_result(records, meta)
    path = save_result(result, out, stem)
    say(f"  Cost: {cost_line(result['summary']['cost'])}")
    return result, path, trace_dir
