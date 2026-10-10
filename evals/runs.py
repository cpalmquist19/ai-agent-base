"""One timestamped folder per eval run.

    evals/results/
        index.html                       every run, newest first (built by `python -m evals dashboard`)
        runs/20261009-150237/            one folder per `run` or `matrix` invocation
            run.json                     what was run, when, on which code, and how it ended
            <provider>__<model>.json     the scored results for each model
            traces/<provider>__<model>/  every prompt, tool call and answer, plus run_log.txt
            comparison.md                the side-by-side table
            dashboard.html               this run's full report
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from evals.cost import annotate_result

MANIFEST = "run.json"
_IGNORE_LINES = ("runs/", "index.html", "*.json", "*.md", "traces/")

# API failures that say nothing about the model (kept in sync with INFRA in dashboard_template.html)
INFRA_RE = re.compile(
    r"(APIConnectionError|APITimeoutError|RateLimitError|InternalServerError|AuthenticationError|PermissionDeniedError"
    r"|NotFoundError|BadRequestError|UnprocessableEntityError|ServiceUnavailable|Overloaded)"
)


def is_infra_error(error: str | None) -> bool:
    return bool(error) and INFRA_RE.search(error) is not None


def runs_root(results_dir: Path) -> Path:
    return results_dir / "runs"


def ensure_gitignore(results_dir: Path) -> None:
    """Results stay on this machine; copy the ones worth keeping into evals/baselines/."""
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / ".gitignore"
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    missing = [line for line in _IGNORE_LINES if line not in existing]
    if missing:
        path.write_text("\n".join(existing + missing) + "\n", encoding="utf-8")


def new_run_dir(results_dir: Path) -> Path:
    """Create ``runs/<YYYYMMDD-HHMMSS>``; a second run in the same second gets ``-2``, ``-3``..."""
    ensure_gitignore(results_dir)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate, n = runs_root(results_dir) / stamp, 2
    while candidate.exists():
        candidate = runs_root(results_dir) / f"{stamp}-{n}"
        n += 1
    candidate.mkdir(parents=True)
    return candidate


def parse_run_id(run_id: str) -> datetime | None:
    try:
        return datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def format_us(run_id: str) -> str:
    """'20261009-150237' -> '10/09/2026 3:02 PM' (US date, 12-hour clock, local time)."""
    when = parse_run_id(run_id)
    if when is None:
        return run_id
    hour = when.hour % 12 or 12
    return f"{when:%m/%d/%Y} {hour}:{when:%M} {'AM' if when.hour < 12 else 'PM'}"


def write_manifest(run_dir: Path, **fields: Any) -> dict[str, Any]:
    """Merge ``fields`` into run.json (created on first call) and return the whole manifest."""
    path = run_dir / MANIFEST
    data: dict[str, Any] = {"id": run_dir.name}
    if path.exists():
        try:
            data.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    data.update(fields)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return data


def read_manifest(run_dir: Path) -> dict[str, Any]:
    data: dict[str, Any] = {"id": run_dir.name}
    try:
        data.update(json.loads((run_dir / MANIFEST).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        data.setdefault("status", "unknown")
    return data


def list_run_dirs(results_dir: Path) -> list[Path]:
    """Run folders, newest first."""
    root = runs_root(results_dir)
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)


def result_files(run_dir: Path) -> list[dict[str, Any]]:
    """The scored results in one run folder, in the order they were produced, with token usage and cost filled in
    (estimated from the saved transcripts for results recorded before usage was tracked)."""
    found = []
    for path in sorted(run_dir.glob("*.json")):
        if path.name == MANIFEST:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and {"meta", "summary", "tasks"} <= set(data):
            found.append({"file": path.name, **annotate_result(data, run_dir=run_dir, stem=path.stem)})
    found.sort(key=lambda r: str(r["meta"].get("timestamp", "")))
    return found


def legacy_result_files(results_dir: Path) -> list[Path]:
    """Old-style result files sitting directly in the results folder."""
    out = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and {"meta", "summary", "tasks"} <= set(data):
            out.append(path)
    return out
