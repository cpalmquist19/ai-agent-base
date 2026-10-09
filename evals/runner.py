"""Run one eval task against a provider and score it."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from lm_studio_chat.chat.engine import run_chat
from lm_studio_chat.chat.prompts import build_system_prompt
from lm_studio_chat.providers.base import LLMProvider
from lm_studio_chat.state import create_app_state

from evals.scoring import ToolCall, score_run

DEFAULT_TIMEOUT_S = 180
_STOP_MARKERS = ("Reached tool-use limit", "_(stopped)_")


@dataclass
class RunContext:
    root: Path
    outside: Path


ProviderFactory = Callable[[RunContext], LLMProvider]


@dataclass
class RunRecord:
    task_id: str
    repeat: int
    passed: bool
    scores: dict[str, float]
    failures: list[str]
    judge: dict[str, Any] | None
    tool_calls: list[dict[str, Any]]
    model_calls: int
    answer: str
    duration_s: float
    error: str | None = None
    trace_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@contextlib.contextmanager
def _sandbox_env() -> Iterator[None]:
    """Evals must run with path confinement ON, whatever the developer's .env says."""
    name = "LM_STUDIO_ALLOW_UNRESTRICTED_PATHS"
    saved = os.environ.pop(name, None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ[name] = saved


def _write_fixtures(base: Path, fixtures: dict[str, str]) -> None:
    for rel, text in fixtures.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def extract_tool_calls(messages: list[dict[str, Any]]) -> list[ToolCall]:
    """Rebuild the ordered tool calls (with full arguments and results) from the transcript."""
    results = {m["tool_call_id"]: str(m.get("content") or "") for m in messages if m.get("role") == "tool"}
    calls: list[ToolCall] = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {"_unparsed": tc["function"]["arguments"]}
            calls.append(ToolCall(tc["function"]["name"], args, results.get(tc["id"], "")))
    return calls


def count_nudges(messages: list[dict[str, Any]]) -> int:
    """Times the engine had to prompt a model that stopped without a tool call or an answer."""
    return sum(
        1
        for m in messages
        if m.get("role") == "user" and str(m.get("content", "")).startswith("You stopped without")
    )


def run_task(
    task: dict[str, Any],
    provider_factory: ProviderFactory,
    *,
    repeat: int = 0,
    judge: Any | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    trace_dir: Path | None = None,
) -> RunRecord:
    started = time.monotonic()
    error: str | None = None
    answer = ""
    messages: list[dict[str, Any]] = []
    tool_calls: list[ToolCall] = []

    with tempfile.TemporaryDirectory(prefix="agent_eval_") as tmp, _sandbox_env():
        base = Path(tmp)
        ctx = RunContext(root=base / "project", outside=base / "outside")
        ctx.root.mkdir()
        ctx.outside.mkdir()
        _write_fixtures(ctx.root, task.get("fixtures", {}))
        _write_fixtures(ctx.outside, task.get("outside_fixtures", {}))
        prompt = task["prompt"].replace("{OUTSIDE}", str(ctx.outside))

        try:
            provider = provider_factory(ctx)
            state = create_app_state(provider=provider, project_root=ctx.root)
            messages = [
                {"role": "system", "content": build_system_prompt(state)},
                {"role": "user", "content": prompt},
            ]
            deadline = started + timeout_s
            final = None
            for partial in run_chat(
                state,
                provider.model_id,
                messages,
                should_cancel=lambda: time.monotonic() > deadline,
            ):
                final = partial
            answer = final.content if final is not None else ""
        except Exception as exc:  # a crashing run is a failed run, not a crashed eval
            error = f"{type(exc).__name__}: {exc}"

        tool_calls = extract_tool_calls(messages)
        finished_cleanly = (
            error is None and bool(answer.strip()) and not any(m in answer for m in _STOP_MARKERS)
        )

        judge_result = None
        if judge is not None and "rubric" in task.get("expect", {}) and finished_cleanly:
            material = "\n\n".join(f"[{name}]\n{text}" for name, text in task.get("fixtures", {}).items())
            judge_result = judge.grade(task, answer, material)

        scored = score_run(
            task,
            tool_calls=tool_calls,
            answer=answer,
            root=ctx.root,
            finished_cleanly=finished_cleanly,
            canaries=task.get("canaries", []),
            judge_result=judge_result,
        )

    trace_path = None
    if trace_dir is not None:
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_file = trace_dir / f"{task['id']}__{repeat}.json"
        trace_file.write_text(
            json.dumps({"task": task["id"], "error": error, "messages": messages[1:]}, indent=2, default=str),
            encoding="utf-8",
        )
        trace_path = str(trace_file)

    return RunRecord(
        task_id=task["id"],
        repeat=repeat,
        passed=scored.passed and error is None,
        scores=scored.scores,
        failures=scored.failures + ([error] if error else []),
        judge=scored.judge,
        tool_calls=[{"name": c.name, "arguments": c.arguments, "ok": c.ok} for c in tool_calls],
        model_calls=sum(1 for m in messages if m.get("role") == "assistant") + (1 if answer else 0),
        answer=answer,
        duration_s=round(time.monotonic() - started, 3),
        error=error,
        trace_path=trace_path,
        extra={"nudges": count_nudges(messages)},
    )
