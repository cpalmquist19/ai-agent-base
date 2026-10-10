"""One-time move of old flat result files into per-run folders.

Before runs had their own folders, every model's result sat directly in ``evals/results/``. The files carry
no record of which ones belonged together, so they are grouped by start time: results that started within
six minutes of the previous one are treated as one run (a ``matrix`` run starts its models back to back).
Files are moved, never deleted or changed.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from evals.runs import ensure_gitignore, legacy_result_files, runs_root, write_manifest

GAP = timedelta(minutes=6)
_STAMP = "%Y%m%d-%H%M%S"


def _when(data: dict[str, Any], path: Path) -> datetime:
    try:
        return datetime.strptime(str(data["meta"].get("timestamp"))[:15], _STAMP)
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime)


def _unique(directory: Path, name: str) -> Path:
    candidate, n = directory / name, 2
    while candidate.exists():
        candidate = directory / f"{Path(name).stem}-{n}{Path(name).suffix}"
        n += 1
    return candidate


def migrate_legacy(results_dir: Path, say: Callable[[str], None] = print) -> int:
    """Move legacy result files into run folders. Returns how many result files were moved."""
    files = []
    for path in legacy_result_files(results_dir):
        data = json.loads(path.read_text(encoding="utf-8"))
        files.append((_when(data, path), path, data))
    if not files:
        say("Nothing to migrate: no old-style result files found.")
        return 0
    files.sort(key=lambda item: item[0])

    groups: list[list[tuple[datetime, Path, dict[str, Any]]]] = [[files[0]]]
    for item in files[1:]:
        if item[0] - groups[-1][-1][0] > GAP:
            groups.append([])
        groups[-1].append(item)

    ensure_gitignore(results_dir)
    root = runs_root(results_dir)
    legacy_md = [p for p in results_dir.glob("matrix_*.md")]
    moved = 0
    for group in groups:
        start, end = group[0][0], group[-1][0]
        run_dir = root / start.strftime(_STAMP)
        if run_dir.exists():
            run_dir = _unique(root, start.strftime(_STAMP) + "-migrated")
        run_dir.mkdir(parents=True)

        targets, tasks, shas, repeats, aborted = [], set(), Counter(), 0, False
        for _when_, path, data in group:
            meta = data["meta"]
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(meta.get("model")))
            target = _unique(run_dir, f"{meta.get('provider')}__{safe}.json")
            old_traces = results_dir / "traces" / path.stem
            shutil.move(str(path), str(target))
            if old_traces.is_dir():
                shutil.move(str(old_traces), str(run_dir / "traces" / target.stem))
            moved += 1
            targets.append(f"{meta.get('provider')}:{meta.get('model')}")
            tasks.update(data["tasks"])
            shas[str(meta.get("git_sha"))] += 1
            repeats = max(repeats, int(meta.get("repeats") or 0))
            aborted = aborted or bool(meta.get("aborted"))

        for md in list(legacy_md):  # the comparison table written at the end of that matrix run
            try:
                stamp = datetime.strptime(md.stem.replace("matrix_", "")[:15], _STAMP)
            except ValueError:
                continue
            if start <= stamp <= end + timedelta(minutes=10):
                shutil.move(str(md), str(_unique(run_dir, "comparison.md")))
                legacy_md.remove(md)

        write_manifest(
            run_dir, kind="migrated", status="partial" if aborted else "complete",
            started=start.isoformat(timespec="seconds"), finished=end.isoformat(timespec="seconds"),
            git_sha=shas.most_common(1)[0][0], repeats=repeats, tasks=sorted(tasks), targets=targets, not_run=[],
            command="migrated from older flat result files (grouped by start time; the finish time is approximate)",
        )
        say(f"  {run_dir.name}: {len(group)} result file(s): {', '.join(targets)}")

    stale = results_dir / "dashboard.html"  # the old single-page dashboard, replaced by index.html
    if stale.exists():
        stale.unlink()
    say(f"Moved {moved} result file(s) into {len(groups)} run folder(s) under {root}.")
    say("Next: python -m evals dashboard --open")
    return moved
