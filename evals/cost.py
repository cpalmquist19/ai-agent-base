"""Token usage and dollar cost for eval runs.

Where the numbers come from:

* **reported** - the provider's own usage report, summed over every model call in a run. This is what you
  are billed for, so it is the figure to trust.
* **estimated** - rebuilt from the saved transcript at about 4 characters per token. Used for runs recorded
  before usage was tracked, and for providers that return no usage. Two things make it rough: it cannot see
  hidden reasoning tokens (so it undercounts reasoning models) and it assumes no prompt caching (so it
  overcounts providers that cache automatically).

Prices live in ``pricing.json`` (USD per 1M tokens). A model with no entry gets token counts but no dollar
figure rather than a guess. Local providers are free.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any

from lm_studio_chat.chat.usage import add_usage, empty_usage

PRICING_PATH = Path(__file__).parent / "pricing.json"
LOCAL_PROVIDERS = frozenset({"lm_studio", "unsloth"})
_DATE_SUFFIX = re.compile(r"-(\d{4}-\d{2}-\d{2}|\d{8})$")  # claude-haiku-4-5-20251001, gpt-x-2026-03-17
# system prompt lines the transcript does not carry: working directory, platform note, skills list
_PROMPT_EXTRAS_TOKENS = 150


# ------------------------------------------------------------------ prices


def load_pricing(path: Path | None = None) -> dict[str, dict[str, float]]:
    """``{model id: {"input", "output", optional "cached_input"}}``, or ``{}`` if the file is unreadable."""
    try:
        data = json.loads((path or PRICING_PATH).read_text(encoding="utf-8"))
        models = data.get("models", {})
        return {k: v for k, v in models.items() if isinstance(v, dict) and "input" in v and "output" in v}
    except (OSError, ValueError, AttributeError):
        return {}


def find_rates(model: str | None, pricing: dict[str, dict[str, float]]) -> dict[str, float] | None:
    """Exact id, or the id without a date suffix. Nothing looser: ``gpt-x-pro`` must not borrow ``gpt-x``'s price."""
    if not model:
        return None
    name = model.removeprefix("models/")
    for candidate in (name, _DATE_SUFFIX.sub("", name)):
        if candidate in pricing:
            return pricing[candidate]
    return None


def output_tokens(usage: dict[str, Any]) -> int:
    """Billed output tokens. Some providers leave thinking tokens out of ``completion_tokens`` but count them in
    ``total_tokens``, so take whichever is larger."""
    prompt, completion, total = (int(usage.get(k) or 0) for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
    return max(completion, total - prompt)


def usage_cost(usage: dict[str, Any], rates: dict[str, float]) -> float:
    prompt = int(usage.get("prompt_tokens") or 0)
    cached = min(int(usage.get("cached_tokens") or 0), prompt)
    cached_rate = rates.get("cached_input", rates["input"])
    return ((prompt - cached) * rates["input"] + cached * cached_rate + output_tokens(usage) * rates["output"]) / 1_000_000


def price_usage(
    provider: str | None, model: str | None, usage: dict[str, Any] | None, pricing: dict[str, dict[str, float]] | None = None
) -> float | None:
    """Dollar cost of ``usage``: 0.0 for local providers, None when the model has no listed price."""
    if provider in LOCAL_PROVIDERS:
        return 0.0
    rates = find_rates(model, load_pricing() if pricing is None else pricing)
    return usage_cost(usage, rates) if rates and usage else None


# ------------------------------------------------------------------ usage of one run


def _tokens(text: Any) -> int:
    return max(1, len(str(text)) // 4) if text else 0


@functools.lru_cache(maxsize=1)
def tool_schema_tokens() -> int:
    try:
        from lm_studio_chat.tools.registry import available_tool_schemas

        return _tokens(json.dumps(available_tool_schemas()))
    except Exception:
        return 0


@functools.lru_cache(maxsize=1)
def system_prompt_tokens() -> int:
    try:
        from lm_studio_chat.config import SYSTEM_PROMPT

        return _tokens(SYSTEM_PROMPT) + _PROMPT_EXTRAS_TOKENS
    except Exception:
        return 0


def _message_tokens(message: dict[str, Any]) -> int:
    content = message.get("content")
    text = content if isinstance(content, str) else json.dumps(content, default=str) if content else ""
    calls = json.dumps(message.get("tool_calls"), default=str) if message.get("tool_calls") else ""
    return _tokens(text) + _tokens(calls) + 4


def estimate_usage(messages: list[dict[str, Any]], answer: str = "", overhead_tokens: int = 0) -> dict[str, Any]:
    """Token usage rebuilt from a transcript. Every assistant turn re-sends everything before it, plus the tool
    schemas (``overhead_tokens``), exactly as the real requests did. ``answer`` is the final reply, which the
    engine returns without appending it to ``messages``."""
    usage: dict[str, Any] = empty_usage()
    context = overhead_tokens
    for message in messages:
        size = _message_tokens(message)
        if message.get("role") == "assistant":
            usage["prompt_tokens"] += context
            usage["completion_tokens"] += size
            usage["calls"] += 1
        context += size
    if answer and answer.strip():
        usage["prompt_tokens"] += context
        usage["completion_tokens"] += _tokens(answer)
        usage["calls"] += 1
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    usage["source"] = "estimated"
    return usage


def finalize_usage(reported: dict[str, Any] | None, messages: list[dict[str, Any]], answer: str) -> dict[str, Any]:
    """The usage to record for a finished run: the provider's report, else an estimate, else an empty record."""
    if reported and reported.get("calls_with_usage"):
        complete = reported["calls_with_usage"] >= reported.get("calls", 0)
        return {**reported, "source": "reported" if complete else "partial"}
    if any(m.get("role") == "assistant" for m in messages) or (answer and answer.strip()):
        return estimate_usage(messages, answer, tool_schema_tokens())
    return {**empty_usage(), "source": "none"}


def merge_usage(*usages: dict[str, Any] | None) -> dict[str, Any] | None:
    """Sum several runs' usage (a retried run costs every attempt, not just the last)."""
    parts = [u for u in usages if u]
    if not parts:
        return None
    merged: dict[str, Any] = empty_usage()
    for u in parts:
        add_usage(merged, u)
    sources = {u.get("source", "reported") for u in parts} - {"none"}
    merged["source"] = sources.pop() if len(sources) == 1 else "mixed" if sources else "none"
    return merged


# ------------------------------------------------------------------ results


def _estimate_from_trace(run_dir: Path | None, stem: str | None, task_id: str, run: dict[str, Any]) -> dict[str, Any] | None:
    if run_dir is None or not stem:
        return None
    path = Path(run_dir) / "traces" / stem / f"{task_id}__{run.get('repeat', 0)}.json"
    try:
        messages = json.loads(path.read_text(encoding="utf-8"))["messages"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return estimate_usage(messages, run.get("answer") or "", tool_schema_tokens() + system_prompt_tokens())


def _source_of(sources: set[str]) -> str:
    sources = sources - {"none"}
    if not sources:
        return "none"
    if sources == {"estimated"}:
        return "estimated"
    if "estimated" in sources or "mixed" in sources:
        return "mixed"
    return "partial" if "partial" in sources else "reported"


def summarize(runs: list[dict[str, Any]], free: bool = False) -> dict[str, Any]:
    """Cost and token totals for a set of annotated runs."""
    usage: dict[str, Any] = empty_usage()
    sources: set[str] = set()
    with_usage = 0
    for run in runs:
        u = run.get("usage")
        if u:
            add_usage(usage, u)
            sources.add(u.get("source", "reported"))
            with_usage += 1
    costs = [r["cost_usd"] for r in runs if r.get("cost_usd") is not None]
    judge = [r["judge_cost_usd"] for r in runs if r.get("judge_cost_usd") is not None]
    passes = sum(1 for r in runs if r.get("passed"))
    total = sum(costs) if costs else None
    return {
        "runs": len(runs),
        "priced_runs": len(costs),
        "total_usd": total,
        "per_run_usd": total / len(costs) if costs else None,
        "per_pass_usd": total / passes if costs and passes else None,
        "passes": passes,
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": output_tokens(usage),
        "cached_tokens": usage["cached_tokens"],
        "reasoning_tokens": usage["reasoning_tokens"],
        "tokens_per_run": (usage["prompt_tokens"] + output_tokens(usage)) / with_usage if with_usage else None,
        "source": _source_of(sources),
        "free": free,
        "judge_usd": sum(judge) if judge else None,
    }


def annotate_result(
    result: dict[str, Any],
    *,
    run_dir: Path | None = None,
    stem: str | None = None,
    pricing: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Add ``usage`` and ``cost_usd`` to every run, and a ``cost`` summary to each task and the result. In place.

    A run that has no usage (saved before tracking existed) is estimated from its transcript under
    ``run_dir/traces/<stem>/`` when that is on disk. A cost already saved with a run is kept, so later price
    changes don't rewrite history; a missing one is filled in from the current price list.
    """
    pricing = load_pricing() if pricing is None else pricing
    meta = result.get("meta", {})
    provider, model = meta.get("provider"), meta.get("model")
    free = provider in LOCAL_PROVIDERS
    rates = None if free else find_rates(model, pricing)

    every: list[dict[str, Any]] = []
    for task_id, task in result.get("tasks", {}).items():
        for run in task.get("runs", []):
            if run.get("usage") is None:
                run["usage"] = _estimate_from_trace(run_dir, stem, task_id, run)
            if run.get("cost_usd") is None:
                usage = run.get("usage")
                run["cost_usd"] = 0.0 if free else (usage_cost(usage, rates) if usage and rates else None)
            judge = run.get("judge") or {}
            if judge.get("usage") and run.get("judge_cost_usd") is None:
                judge_rates = find_rates(judge.get("model"), pricing)
                run["judge_cost_usd"] = usage_cost(judge["usage"], judge_rates) if judge_rates else None
            every.append(run)
        task["cost"] = summarize(task.get("runs", []), free)
    result.setdefault("summary", {})["cost"] = summarize(every, free)
    return result


# ------------------------------------------------------------------ display


def format_usd(value: float | None, *, free: bool = False) -> str:
    if free:
        return "free"
    if value is None:
        return "n/a"
    if value == 0:
        return "$0"
    if value < 0.01:
        return f"${value:.4f}"
    if value < 1:
        return f"${value:.3f}"
    return f"${value:,.2f}"


def format_tokens(count: float | None) -> str:
    if count is None:
        return "n/a"
    if count < 1000:
        return str(int(round(count)))
    if count < 1_000_000:
        return f"{count / 1000:.1f}k"
    return f"{count / 1_000_000:.2f}M"


def describe_usage(provider: str | None, model: str | None, usage: dict[str, Any] | None, pricing: dict | None = None) -> str:
    """One short line for the console: ``12.3k in / 450 out  $0.0031`` (``~`` marks an estimate)."""
    if not usage or usage.get("source") == "none":
        return ""
    cost = price_usage(provider, model, usage, pricing)
    mark = "~" if usage.get("source") in ("estimated", "partial") else ""
    if provider in LOCAL_PROVIDERS:
        price = "free"
    else:
        price = "no price" if cost is None else mark + format_usd(cost)
    return f"{mark}{format_tokens(usage['prompt_tokens'])} in / {format_tokens(output_tokens(usage))} out  {price}"


def cost_line(cost: dict[str, Any]) -> str:
    """The end-of-model summary: ``$0.4821 total, $0.0146/run, $0.0201/passing run``."""
    if cost.get("free"):
        return "free (local model)"
    if cost.get("total_usd") is None:
        return f"{format_tokens(cost['prompt_tokens'])} in / {format_tokens(cost['completion_tokens'])} out tokens; " \
               "no price listed in evals/pricing.json, so no dollar figure"
    mark = "~" if cost.get("source") in ("estimated", "partial", "mixed") else ""
    parts = [f"{mark}{format_usd(cost['total_usd'])} total", f"{mark}{format_usd(cost['per_run_usd'])}/run"]
    if cost.get("per_pass_usd") is not None:
        parts.append(f"{mark}{format_usd(cost['per_pass_usd'])}/passing run")
    if cost.get("judge_usd"):
        parts.append(f"plus {format_usd(cost['judge_usd'])} for the judge")
    return ", ".join(parts)
