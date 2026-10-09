"""Aggregate run records, render comparison tables, and gate on regressions."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from evals.scoring import DIMENSIONS


def build_result(records: list[Any], meta: dict[str, Any]) -> dict[str, Any]:
    by_task: dict[str, list[Any]] = defaultdict(list)
    for r in records:
        by_task[r.task_id].append(r)

    tasks: dict[str, Any] = {}
    for task_id, runs in by_task.items():
        tasks[task_id] = {
            "runs": [r.to_dict() for r in runs],
            "pass_rate": mean(r.passed for r in runs),
            "mean_scores": {d: mean(r.scores[d] for r in runs) for d in DIMENSIONS},
            "mean_duration_s": mean(r.duration_s for r in runs),
            "mean_nudges": mean(r.extra.get("nudges", 0) for r in runs),
        }
    all_runs = [r for runs in by_task.values() for r in runs]
    summary = {
        "tasks": len(tasks),
        "runs": len(all_runs),
        "pass_rate": mean(r.passed for r in all_runs) if all_runs else 0.0,
        "mean_scores": {d: mean(r.scores[d] for r in all_runs) for d in DIMENSIONS} if all_runs else {},
        "mean_duration_s": mean(r.duration_s for r in all_runs) if all_runs else 0.0,
        "mean_nudges": mean(r.extra.get("nudges", 0) for r in all_runs) if all_runs else 0.0,
    }
    return {"meta": meta, "summary": summary, "tasks": tasks}


def _clip(text: Any, limit: int) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def render_run(record: Any, prompt: str, *, limit: int = 400) -> str:
    """A short human-readable account of one run: task, tool calls, answer, why it failed."""
    status = "PASS" if record.passed else "FAIL"
    lines = [
        f"--- {record.task_id}  run {record.repeat + 1}  [{status}]  {record.duration_s:.1f}s ---",
        f"Task:   {_clip(prompt, limit)}",
    ]
    for i, call in enumerate(record.tool_calls, 1):
        mark = "ok " if call["ok"] else "ERR"
        lines.append(f"  {i}. {mark} {call['name']}  {_clip(json.dumps(call['arguments']), 140)}")
    if not record.tool_calls:
        lines.append("  (no tool calls)")
    lines.append(f"Answer: {_clip(record.answer or '(empty)', limit)}")
    for failure in record.failures:
        lines.append(f"  ! {failure}")
    return "\n".join(lines)


def save_run_log(records: list[Any], prompts: dict[str, str], directory: Path) -> Path:
    """Write every run so far, unclipped, to run_log.txt next to the traces."""
    directory.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(render_run(r, prompts.get(r.task_id, ""), limit=100_000) for r in records)
    path = directory / "run_log.txt"
    path.write_text(body + "\n", encoding="utf-8")
    return path


def save_result(result: dict[str, Any], directory: Path, stem: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    ignore = directory / ".gitignore"
    if not ignore.exists():  # raw results stay local; copy keepers to evals/baselines/
        ignore.write_text("*.json\ntraces/\n", encoding="utf-8")
    path = directory / f"{stem}.json"
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return path


def load_result(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_markdown(results: list[dict[str, Any]]) -> str:
    """One row per model/run file, with overall and per-task pass rates."""
    task_ids = sorted({t for r in results for t in r["tasks"]})
    head = ["Model", "Pass", "Tool sel.", "Args ok", "Efficiency", "Nudges/run", "Avg s/run", "Repeats", *task_ids]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for r in results:
        s, meta = r["summary"], r["meta"]
        row = [
            f"{meta.get('provider', '?')}:{meta.get('model', '?')}",
            f"{s['pass_rate']:.0%}",
            f"{s['mean_scores'].get('tool_selection', 0):.2f}",
            f"{s['mean_scores'].get('args_valid', 0):.2f}",
            f"{s['mean_scores'].get('efficiency', 0):.2f}",
            f"{s.get('mean_nudges', 0):.1f}",
            f"{s['mean_duration_s']:.1f}",
            str(meta.get("repeats", 1)),
        ]
        for tid in task_ids:
            t = r["tasks"].get(tid)
            row.append(f"{t['pass_rate']:.0%}" if t else "-")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def check_regression(result: dict[str, Any], baseline: dict[str, Any], max_drop: float = 0.0) -> list[str]:
    """List every task whose pass rate fell more than ``max_drop`` below the baseline."""
    problems = []
    for task_id, base in baseline["tasks"].items():
        current = result["tasks"].get(task_id)
        if current is None:
            problems.append(f"{task_id}: present in baseline but not run")
        elif current["pass_rate"] < base["pass_rate"] - max_drop:
            problems.append(f"{task_id}: pass rate {current['pass_rate']:.0%} < baseline {base['pass_rate']:.0%}")
    return problems
