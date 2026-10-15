"""Check the evals against scripted good and bad agents (no model, no network)."""

from __future__ import annotations

from evals.fake import ScriptedClient
from evals.policies import POLICIES, Policy
from evals.runner import RunContext, RunRecord, run_task
from evals.tasks import load_tasks
from relay.providers.base import LLMProvider


def scripted_provider_factory(policy: Policy):
    def factory(ctx: RunContext) -> LLMProvider:
        return LLMProvider(
            id="scripted",
            label="Scripted reference model",
            client=ScriptedClient(policy.build(ctx)),  # type: ignore[arg-type]
            model_id="scripted",
            base_url="",
            stream_usage=False,
            local=True,
        )

    return factory


def failing_dimensions(record: RunRecord) -> frozenset[str]:
    return frozenset(dim for dim, value in record.scores.items() if value < 1.0)


def judge_policy(task_id: str, name: str, policy: Policy, record: RunRecord) -> str | None:
    """Return a problem description, or None if the scorer behaved as the policy demands."""
    failing = failing_dimensions(record)
    if policy.is_good:
        if record.passed and not failing:
            return None
        return f"{task_id}/{name}: reference solution did not score perfectly: failing={sorted(failing)} {record.failures}"
    if record.passed:
        return f"{task_id}/{name}: bad behaviour was NOT caught (run passed); expected failures in {sorted(policy.expect_fail)}"
    if failing != policy.expect_fail:
        return (
            f"{task_id}/{name}: expected failing dimensions {sorted(policy.expect_fail)} "
            f"but got {sorted(failing)} ({record.failures})"
        )
    return None


def run_selfcheck(verbose: bool = True) -> list[str]:
    problems: list[str] = []
    rows = 0
    for task in load_tasks():
        policies = POLICIES.get(task["id"], {})
        if "good" not in policies:
            problems.append(f"{task['id']}: no 'good' reference policy (every task needs a known-good solution)")
            continue
        if len(policies) < 2:
            problems.append(f"{task['id']}: no deliberately-bad policy (every task must prove it can fail)")
        for name, policy in policies.items():
            record = run_task(task, scripted_provider_factory(policy))
            problem = judge_policy(task["id"], name, policy, record)
            rows += 1
            if verbose:
                kind = "reference" if policy.is_good else "bad     "
                status = "ok  " if problem is None else "FAIL"
                dims = ",".join(sorted(failing_dimensions(record))) or "-"
                print(f"  [{status}] {task['id']:<22} {kind} {name:<26} failing: {dims}")
            if problem:
                problems.append(problem)
    if verbose:
        print(f"{rows} scripted runs, {len(problems)} problem(s)")
    return problems
