"""Command line: ``python -m evals {selfcheck,run,report,check}``."""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5, cwd=Path(__file__).parent
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _live_provider(provider: str, model: str | None):
    """Build a real provider from environment settings plus CLI overrides."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    os.environ["LLM_PROVIDER"] = provider
    if model:
        model_env = {
            "lm_studio": "LM_STUDIO_MODEL",
            "openai": "OPENAI_MODEL",
            "anthropic": "ANTHROPIC_MODEL",
            "unsloth": "UNSLOTH_MODEL",
        }[provider]
        os.environ[model_env] = model
    from lm_studio_chat.providers import create_provider

    return create_provider()


def cmd_selfcheck(_: argparse.Namespace) -> int:
    from evals.selfcheck import run_selfcheck

    problems = run_selfcheck()
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


def cmd_run(args: argparse.Namespace) -> int:
    from evals.judge import LLMJudge
    from evals.report import build_result, render_markdown, render_run, save_result, save_run_log
    from evals.runner import run_task
    from evals.tasks import load_tasks

    provider = _live_provider(args.provider, args.model)
    judge = None
    if args.judge:
        jp = _live_provider(args.judge_provider, args.judge_model) if args.judge_provider else provider
        judge = LLMJudge(
            jp.client, jp.model_id, omit_temperature=jp.omit_temperature
        )

    tasks = load_tasks(args.tasks.split(",") if args.tasks else None)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", provider.model_id)
    stem = f"{stamp}__{provider.id}__{safe_model}"
    trace_dir = Path(args.out) / "traces" / stem

    print(f"Running {len(tasks)} task(s) x {args.repeats} on {provider.id}:{provider.model_id}")
    records = []
    prompts: dict[str, str] = {}
    for task in tasks:
        for repeat in range(args.repeats):
            rec = run_task(
                task,
                lambda _ctx: provider,
                repeat=repeat,
                judge=judge,
                timeout_s=args.timeout,
                trace_dir=trace_dir,
            )
            records.append(rec)
            prompts[task["id"]] = task["prompt"]
            if args.verbose:
                print(render_run(rec, task["prompt"]))
                print()
            else:
                mark = "PASS" if rec.passed else "FAIL"
                print(f"  [{mark}] {task['id']:<22} run {repeat + 1}/{args.repeats}  {rec.duration_s:>6.1f}s  calls={len(rec.tool_calls)}")
                for failure in rec.failures:
                    print(f"         - {failure}")
            save_run_log(records, prompts, trace_dir)  # readable full log, refreshed after every run

    meta = {
        "provider": provider.id,
        "model": provider.model_id,
        "repeats": args.repeats,
        "timestamp": stamp,
        "git_sha": _git_sha(),
        "judge": bool(judge),
    }
    result = build_result(records, meta)
    path = save_result(result, Path(args.out), stem)
    print()
    print(render_markdown([result]))
    print(f"\nSaved {path}")
    print(f"Readable log of every run: {trace_dir / 'run_log.txt'}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from evals.report import load_result, render_markdown

    print(render_markdown([load_result(Path(p)) for p in args.files]))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from evals.report import check_regression, load_result

    problems = check_regression(load_result(Path(args.result)), load_result(Path(args.baseline)), args.max_drop)
    for p in problems:
        print("REGRESSION:", p)
    print("OK, no regressions" if not problems else f"{len(problems)} regression(s)")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("selfcheck", help="validate the evals using scripted good/bad agents (no model needed)").set_defaults(
        fn=cmd_selfcheck
    )

    _providers = ("lm_studio", "openai", "anthropic", "unsloth")
    run = sub.add_parser("run", help="run the tasks against a real model")
    run.add_argument("--provider", choices=_providers, default="lm_studio")
    run.add_argument(
        "--model",
        help="model id (default: loaded LM Studio / Unsloth model, or OPENAI_MODEL / ANTHROPIC_MODEL)",
    )
    run.add_argument("--tasks", help="comma-separated task ids (default: all)")
    run.add_argument("--repeats", type=int, default=3, help="runs per task; models are non-deterministic")
    run.add_argument("--timeout", type=float, default=180, help="seconds allowed per run")
    run.add_argument("--verbose", "-v", action="store_true", help="print each run's task, tool calls and answer as it finishes")
    run.add_argument("--judge", action="store_true", help="grade rubric tasks with an LLM judge")
    run.add_argument("--judge-provider", choices=_providers, help="use a different model as judge")
    run.add_argument("--judge-model")
    run.add_argument("--out", default=str(RESULTS_DIR))
    run.set_defaults(fn=cmd_run)

    rep = sub.add_parser("report", help="compare saved result files side by side")
    rep.add_argument("files", nargs="+")
    rep.set_defaults(fn=cmd_report)

    chk = sub.add_parser("check", help="fail if any task's pass rate dropped versus a baseline result")
    chk.add_argument("result")
    chk.add_argument("--baseline", required=True)
    chk.add_argument("--max-drop", type=float, default=0.0)
    chk.set_defaults(fn=cmd_check)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
