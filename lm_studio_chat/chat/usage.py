"""Token usage bookkeeping shared by the chat engine and the eval harness."""

from __future__ import annotations

from typing import Any

COUNT_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "reasoning_tokens")
# calls = model requests made; calls_with_usage = how many of them reported token counts
USAGE_KEYS = (*COUNT_KEYS, "calls", "calls_with_usage")


def empty_usage() -> dict[str, int]:
    return dict.fromkeys(USAGE_KEYS, 0)


def _count(obj: Any, name: str) -> int:
    value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def read_usage(usage: Any) -> dict[str, int]:
    """Token counts from an OpenAI-style ``usage`` object, tolerating providers that leave parts out."""
    prompt = _count(usage, "prompt_tokens")
    completion = _count(usage, "completion_tokens")
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": _count(usage, "total_tokens") or prompt + completion,
        "cached_tokens": _count(getattr(usage, "prompt_tokens_details", None), "cached_tokens"),
        "reasoning_tokens": _count(getattr(usage, "completion_tokens_details", None), "reasoning_tokens"),
    }


def add_usage(total: dict[str, int], other: dict[str, Any] | None) -> dict[str, int]:
    """Add ``other`` into ``total`` in place and return it."""
    for key in USAGE_KEYS:
        total[key] = total.get(key, 0) + int((other or {}).get(key) or 0)
    return total
