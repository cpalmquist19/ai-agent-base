"""Load and validate eval task definitions from evals/tasks/*.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TASKS_DIR = Path(__file__).parent / "tasks"

_TOP_KEYS = {"id", "category", "description", "prompt", "fixtures", "outside_fixtures", "canaries", "expect"}
_EXPECT_KEYS = {
    "steps",
    "forbidden_tools",
    "max_tool_calls",
    "allow_tool_errors",
    "files",
    "python_check",
    "answer",
    "rubric",
    "unchanged_files",
    "hidden_tests",
    "mutation_check",
}


class TaskError(ValueError):
    pass


def validate_task(task: dict[str, Any], source: str = "<task>") -> None:
    for key in ("id", "prompt", "expect"):
        if key not in task:
            raise TaskError(f"{source}: missing required key {key!r}")
    unknown = set(task) - _TOP_KEYS
    if unknown:
        raise TaskError(f"{source}: unknown keys {sorted(unknown)}")
    unknown = set(task["expect"]) - _EXPECT_KEYS
    if unknown:
        raise TaskError(f"{source}: unknown expect keys {sorted(unknown)}")
    for step in task["expect"].get("steps", []):
        tool = step.get("tool")
        names = tool if isinstance(tool, list) else [tool]
        if not names or not all(isinstance(n, str) and n for n in names):
            raise TaskError(f"{source}: every step needs a 'tool' (a name, or a list of acceptable names)")
    for rel in task["expect"].get("unchanged_files", []):
        if rel not in task.get("fixtures", {}):
            raise TaskError(f"{source}: unchanged_files lists {rel!r}, which is not a fixture")
    if "{OUTSIDE}" in task["prompt"] and not task.get("outside_fixtures"):
        raise TaskError(f"{source}: prompt uses {{OUTSIDE}} but there are no outside_fixtures")
    for canary in task.get("canaries", []):
        if not any(canary in text for text in task.get("outside_fixtures", {}).values()):
            raise TaskError(f"{source}: canary {canary!r} does not appear in any outside fixture")


def load_tasks(only: list[str] | None = None, directory: Path = TASKS_DIR) -> list[dict[str, Any]]:
    tasks = []
    for path in sorted(directory.glob("*.json")):
        task = json.loads(path.read_text(encoding="utf-8"))
        validate_task(task, path.name)
        if task["id"] != path.stem:
            raise TaskError(f"{path.name}: id {task['id']!r} must match the file name")
        tasks.append(task)
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise TaskError("duplicate task ids")
    if only:
        missing = set(only) - set(ids)
        if missing:
            raise TaskError(f"unknown tasks: {sorted(missing)}; available: {ids}")
        tasks = [t for t in tasks if t["id"] in only]
    return tasks
