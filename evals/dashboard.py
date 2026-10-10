"""Build the HTML reports: one self-contained page per run, and an index of every run.

    python -m evals dashboard                 # rebuild everything, no browser
    python -m evals dashboard --open          # ...and open the index (all runs, newest first)
    python -m evals dashboard --run 20261009-150237 --open     # open one run's report

Pages have no server and no external requests. All data is embedded, so a run folder's
dashboard.html can be emailed or opened offline.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from evals.runs import (
    format_us,
    is_infra_error,
    legacy_result_files,
    list_run_dirs,
    read_manifest,
    result_files,
)

RUN_TEMPLATE = Path(__file__).parent / "dashboard_template.html"
INDEX_TEMPLATE = Path(__file__).parent / "index_template.html"
DEFAULT_RESULTS = Path(__file__).parent / "results"


def task_catalog() -> dict[str, dict[str, str]]:
    from evals.tasks import load_tasks

    return {
        t["id"]: {
            "category": t.get("category", "other"),
            "description": t.get("description", ""),
            "prompt": t["prompt"].replace("{OUTSIDE}", "<a folder outside the project>"),
        }
        for t in load_tasks()
    }


def _embed(template_path: Path, payload: dict[str, Any]) -> str:
    template = template_path.read_text(encoding="utf-8")
    # "</" inside JSON could close the script tag early; "<\/" is the same string to a JSON parser
    data = json.dumps(payload, default=str).replace("</", "<\\/")
    return template.replace("__EVAL_DATA__", data)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def model_summary(result: dict[str, Any]) -> dict[str, Any]:
    """One model's headline numbers. Runs that died on an API error measured nothing, so they are left out."""
    every = [run for t in result["tasks"].values() for run in t["runs"]]
    scored = [run for run in every if not is_infra_error(run.get("error"))]
    per_task: dict[str, list[int]] = {}
    for tid, t in result["tasks"].items():
        kept = [run for run in t["runs"] if not is_infra_error(run.get("error"))]
        per_task[tid] = [sum(1 for r in kept if r["passed"]), len(kept)]
    meta = result["meta"]
    cost = result.get("summary", {}).get("cost") or {}
    return {
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "n": len(scored),
        "passed": sum(1 for r in scored if r["passed"]),
        "errored": len(every) - len(scored),
        "seconds": _mean([r["duration_s"] for r in scored]),
        "args_valid": _mean([r["scores"].get("args_valid", 1.0) for r in scored]),
        "safety_failures": sum(1 for r in scored if r["scores"].get("safety", 1.0) < 1.0),
        "aborted": meta.get("aborted"),
        "per_task": per_task,
        "cost_usd": cost.get("total_usd"),
        "cost_per_run": cost.get("per_run_usd"),
        "cost_per_pass": cost.get("per_pass_usd"),
        "cost_source": cost.get("source"),
        "free": bool(cost.get("free")),
    }


def _seconds_between(start: str | None, end: str | None) -> float | None:
    try:
        return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def run_summary(run_dir: Path) -> dict[str, Any]:
    manifest = read_manifest(run_dir)
    results = result_files(run_dir)
    models = [model_summary(r) for r in results]
    spent = [m["cost_usd"] for m in models if m["cost_usd"] is not None and not m["free"]]
    return {
        "id": run_dir.name,
        "label": format_us(run_dir.name),
        "href": f"runs/{run_dir.name}/dashboard.html",
        "kind": manifest.get("kind", "run"),
        "status": manifest.get("status", "unknown"),
        "git_sha": manifest.get("git_sha"),
        "repeats": manifest.get("repeats"),
        "tasks": manifest.get("tasks") or sorted({t for r in results for t in r["tasks"]}),
        "not_run": manifest.get("not_run", []),
        # migrated runs have no recorded finish time, so a duration would be a made-up number
        "seconds": None if manifest.get("kind") == "migrated" else _seconds_between(manifest.get("started"), manifest.get("finished")),
        "models": models,
        "cost_usd": sum(spent) if spent else None,  # what the run spent on paid models; None if nothing was priced
        "cost_estimated": any(m["cost_source"] in ("estimated", "partial", "mixed") for m in models),
        "cost_unpriced": sum(1 for m in models if m["cost_usd"] is None and not m["free"] and m["n"] > 0),
    }


def write_run_dashboard(run_dir: Path) -> Path:
    payload = {
        "generated": time.strftime("%m/%d/%Y %I:%M %p").lstrip("0"),
        "run": {**read_manifest(run_dir), "label": format_us(run_dir.name), "folder": str(run_dir)},
        "results": result_files(run_dir),
        "tasks": task_catalog(),
        "indexHref": "../../index.html",
    }
    path = run_dir / "dashboard.html"
    path.write_text(_embed(RUN_TEMPLATE, payload), encoding="utf-8")
    return path


def write_index(results_dir: Path) -> Path:
    payload = {
        "generated": time.strftime("%m/%d/%Y %I:%M %p").lstrip("0"),
        "runs": [run_summary(d) for d in list_run_dirs(results_dir)],
        "tasks": task_catalog(),
    }
    path = results_dir / "index.html"
    results_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(_embed(INDEX_TEMPLATE, payload), encoding="utf-8")
    return path


def build_all(results_dir: Path) -> tuple[Path | None, list[Path]]:
    """Rebuild every run's report and the index. (None, []) if there are no runs yet."""
    run_dirs = list_run_dirs(results_dir)
    if not run_dirs:
        return None, []
    pages = [write_run_dashboard(d) for d in run_dirs]
    return write_index(results_dir), pages


def cmd_dashboard(args: Any) -> int:
    import webbrowser

    results_dir = Path(args.results or DEFAULT_RESULTS)
    legacy = legacy_result_files(results_dir)
    if legacy:
        print(f"Found {len(legacy)} result file(s) from before runs got their own folders. "
              "Move them in with: python -m evals migrate")
    index, pages = build_all(results_dir)
    if index is None:
        print(f"No runs found in {results_dir / 'runs'}. Run `python -m evals run` or `matrix` first.")
        return 1
    print(f"Built {len(pages)} run report(s) and the index: {index}")
    target = index
    if args.run:
        target = results_dir / "runs" / args.run / "dashboard.html"
        if not target.exists():
            print(f"No run named {args.run!r}. Newest runs: {', '.join(d.name for d in list_run_dirs(results_dir)[:5])}")
            return 2
        print(f"Run report: {target}")
    if args.open:
        webbrowser.open(target.resolve().as_uri())
    return 0
