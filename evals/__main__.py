"""Command line: ``python -m evals {selfcheck,run,matrix,dashboard,report,check}``."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


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
            "google": "GOOGLE_AI_STUDIO_MODEL",
            "unsloth": "UNSLOTH_MODEL",
        }[provider]
        os.environ[model_env] = model
    elif provider in ("lm_studio", "unsloth"):  # "whichever is loaded": don't carry over an earlier pin
        os.environ.pop({"lm_studio": "LM_STUDIO_MODEL", "unsloth": "UNSLOTH_MODEL"}[provider], None)
    from lm_studio_chat.providers import create_provider

    return create_provider()


def _one_provider(value: str) -> str:
    """argparse type for `run`, which tests a single provider; point comma lists at `matrix`."""
    if "," in value:
        raise argparse.ArgumentTypeError(
            f"'run' tests one provider at a time. To run several ({value}), use: "
            f"python -m evals matrix --providers {value}"
        )
    return value


def cmd_selfcheck(_: argparse.Namespace) -> int:
    from evals.selfcheck import run_selfcheck

    problems = run_selfcheck()
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


def cmd_run(args: argparse.Namespace) -> int:
    from evals.execute import run_model
    from evals.judge import LLMJudge
    from evals.report import render_markdown
    from evals.tasks import load_tasks

    provider = _live_provider(args.provider, args.model)
    judge = None
    if args.judge:
        jp = _live_provider(args.judge_provider, args.judge_model) if args.judge_provider else provider
        judge = LLMJudge(jp.client, jp.model_id, omit_temperature=jp.omit_temperature)

    from evals.execute import ModelUnavailable, git_sha
    from evals.runs import format_us, new_run_dir, write_manifest

    tasks = load_tasks(args.tasks.split(",") if args.tasks else None)
    results_dir = Path(args.out)
    run_dir = new_run_dir(results_dir)
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    write_manifest(run_dir, kind="run", status="running", started=started, git_sha=git_sha(), repeats=args.repeats,
                   tasks=[t["id"] for t in tasks], targets=[f"{provider.id}:{provider.model_id}"], command=" ".join(sys.argv[1:]))
    print(f"Run folder: {run_dir}  ({format_us(run_dir.name)})")

    status, not_run = "complete", []
    try:
        result, path, trace_dir = run_model(
            provider, tasks, repeats=args.repeats, timeout=args.timeout, judge=judge, out=run_dir, verbose=args.verbose
        )
        if result["meta"].get("aborted"):
            status = "incomplete"
    except ModelUnavailable as exc:
        print(f"\nCould not run {provider.id}:{provider.model_id}: {exc.reason}")
        status, not_run, result = "failed", [{"model": f"{provider.id}:{provider.model_id}", "reason": exc.reason}], None
    write_manifest(run_dir, status=status, not_run=not_run, finished=time.strftime("%Y-%m-%dT%H:%M:%S"))
    _refresh_reports(results_dir, run_dir)
    if result is None:
        return 1
    print()
    print(render_markdown([result]))
    print(f"\nSaved {path}")
    print(f"Readable log of every run: {trace_dir / 'run_log.txt'}")
    return 0


def _refresh_reports(results_dir: Path, run_dir: Path) -> None:
    """Rebuild this run's report and the index; never let a reporting problem fail the run itself."""
    try:
        from evals.dashboard import write_index, write_run_dashboard

        page = write_run_dashboard(run_dir)
        index = write_index(results_dir)
        print(f"\nReport for this run: {page}\nAll runs:            {index}   (or: python -m evals dashboard --open)")
    except Exception as exc:
        print(f"\n(Could not build the report: {type(exc).__name__}: {exc})")


def cmd_matrix(args: argparse.Namespace) -> int:
    from evals.matrix import cmd_matrix as run_matrix_command

    return run_matrix_command(args)


def cmd_dashboard(args: argparse.Namespace) -> int:
    from evals.dashboard import cmd_dashboard as build_dashboard

    return build_dashboard(args)


def cmd_migrate(args: argparse.Namespace) -> int:
    from evals.migrate import migrate_legacy

    moved = migrate_legacy(Path(args.results or RESULTS_DIR))
    return 0 if moved >= 0 else 1


def cmd_report(args: argparse.Namespace) -> int:
    from evals.cost import annotate_result
    from evals.report import load_result, render_markdown

    import glob

    results = []
    for name in args.files:
        # Windows shells pass "*.json" through untouched, so expand it here
        for match in sorted(glob.glob(name)) or [name]:
            path = Path(match)
            data = load_result(path)
            if not (isinstance(data.get("tasks"), dict) and "meta" in data):  # e.g. a run folder's run.json
                continue
            # results saved before cost tracking get an estimate from the transcripts next to them
            results.append(annotate_result(data, run_dir=path.parent, stem=path.stem))
    if not results:
        print("No result files found. Pass the model result files from a run folder, e.g. evals/results/runs/<run>/*.json")
        return 1
    print(render_markdown(results))
    print("\n$/pass = cost per passing run. ~ = estimated from transcripts, not reported by the provider.")
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

    _providers = ("lm_studio", "openai", "anthropic", "google", "unsloth")
    run = sub.add_parser("run", help="run the tasks against one real model")
    run.add_argument("--provider", type=_one_provider, choices=_providers, default="lm_studio")
    run.add_argument(
        "--model",
        help="model id (default: loaded LM Studio / Unsloth model, or OPENAI_MODEL / ANTHROPIC_MODEL / GOOGLE_AI_STUDIO_MODEL)",
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

    mx = sub.add_parser(
        "matrix",
        help="run many providers/models in one go (interactive menu if you pass no --providers/--models)",
        description="Run the evals against several providers and models in one command and compare them.",
    )
    mx.add_argument("--providers", help="comma-separated: openai,anthropic,google,lm_studio,unsloth (each provider's default models)")
    mx.add_argument(
        "--models",
        help="comma-separated provider:model pairs, e.g. openai:gpt-5.6-terra,anthropic:claude-sonnet-5-5 "
        "(a bare 'lm_studio' means whichever model is loaded)",
    )
    mx.add_argument("--repeats", type=int, help="runs per task (default from evals/matrix_defaults.json)")
    mx.add_argument("--tasks", help="comma-separated task ids (default: all)")
    mx.add_argument("--timeout", type=float, help="seconds allowed per run")
    mx.add_argument("--judge", action="store_true", help="grade rubric tasks with an LLM judge")
    mx.add_argument("--judge-provider", choices=_providers)
    mx.add_argument("--judge-model")
    mx.add_argument("--verbose", "-v", action="store_true", help="print every run's task, tool calls and answer")
    mx.add_argument("--dry-run", action="store_true", help="show the plan and exit without running")
    mx.add_argument("--no-menu", action="store_true", help="never prompt; with no options, run each ready provider's defaults")
    mx.add_argument("--out", default=None)
    mx.set_defaults(fn=cmd_matrix)

    dash = sub.add_parser("dashboard", help="build the HTML reports: an index of all runs plus one report per run")
    dash.add_argument("--results", help="the results folder (default: evals/results)")
    dash.add_argument("--run", help="open this run's report (a folder name such as 20261009-150237) instead of the index")
    dash.add_argument("--open", action="store_true", help="open it in your browser when done")
    dash.set_defaults(fn=cmd_dashboard)

    mig = sub.add_parser("migrate", help="move old flat result files into per-run folders (one-time)")
    mig.add_argument("--results", help="the results folder (default: evals/results)")
    mig.set_defaults(fn=cmd_migrate)

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
