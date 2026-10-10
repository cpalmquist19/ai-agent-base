"""Deterministic stand-in for an OpenAI-compatible streaming client.

The chat engine only needs ``client.chat.completions.create(**kwargs)`` to return an
iterator of chunks shaped like the OpenAI SDK's streaming chunks. ``ScriptedClient``
replays a fixed script, one step per model call, so engine behaviour and the eval
scorer can be tested without a model, a network, or an API key.

A step is one of:
    {"content": "text"}                              -> plain answer
    {"tool_calls": [{"name": ..., "arguments": {}}]} -> one or more tool calls
    {}                                               -> empty stop (no text, no tools)
"""

from __future__ import annotations

import json
from types import SimpleNamespace as NS
from typing import Any, Iterator


class ScriptExhausted(AssertionError):
    """The engine asked the model for more rounds than the script provides."""


def say(text: str) -> dict[str, Any]:
    return {"content": text}


def call(name: str, **arguments: Any) -> dict[str, Any]:
    return {"tool_calls": [{"name": name, "arguments": arguments}]}


def calls(*tool_calls: dict[str, Any]) -> dict[str, Any]:
    """Several tool calls in one model turn."""
    merged: list[dict[str, Any]] = []
    for tc in tool_calls:
        merged.extend(tc["tool_calls"])
    return {"tool_calls": merged}


def gemini_calls(*tool_calls: dict[str, Any]) -> dict[str, Any]:
    """Several tool calls streamed the way Gemini's OpenAI-compatible endpoint does."""
    return {**calls(*tool_calls), "gemini_style": True}


EMPTY: dict[str, Any] = {}


def _chunk(
    *,
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish: str | None = None,
) -> Any:
    delta = NS(content=content, tool_calls=tool_calls)
    return NS(choices=[NS(delta=delta, finish_reason=finish)], usage=None)


def _chunks_for(step: dict[str, Any], call_no: int) -> Iterator[Any]:
    text = step.get("content")
    if text:
        for i in range(0, len(text), 12):  # stream in small pieces, like a real model
            yield _chunk(content=text[i : i + 12])

    for index, tc in enumerate(step.get("tool_calls", [])):
        args = tc.get("arguments", {})
        args_json = args if isinstance(args, str) else json.dumps(args)
        tc_id = f"call_{call_no}_{index}"
        if step.get("gemini_style"):
            # Gemini's OpenAI-compatible stream: no index, one whole call per chunk, and a
            # thought_signature on the first call that must be echoed back.
            delta = NS(index=None, id=tc_id, function=NS(name=tc["name"], arguments=args_json))
            if index == 0:
                delta.extra_content = {"google": {"thought_signature": f"sig_{call_no}"}}
            yield _chunk(tool_calls=[delta])
            continue
        half = max(1, len(args_json) // 2)
        # Split name and arguments across chunks to exercise the engine's accumulator.
        yield _chunk(
            tool_calls=[
                NS(
                    index=index,
                    id=tc_id,
                    function=NS(name=tc["name"], arguments=args_json[:half]),
                )
            ]
        )
        yield _chunk(
            tool_calls=[
                NS(index=index, id=None, function=NS(name=None, arguments=args_json[half:]))
            ]
        )

    finish = "tool_calls" if step.get("tool_calls") else "stop"
    yield _chunk(finish=finish)
    yield NS(
        choices=[],
        usage=NS(prompt_tokens=10 * call_no, completion_tokens=5, total_tokens=10 * call_no + 5),
    )


class ScriptedClient:
    """Duck-typed ``openai.OpenAI`` replacement driven by a script."""

    def __init__(self, script: list[dict[str, Any]], *, reject_params: tuple[str, ...] = ()):
        self._script = list(script)
        self._reject = reject_params
        self.requests: list[dict[str, Any]] = []
        self.chat = NS(completions=NS(create=self._create))

    @property
    def calls_made(self) -> int:
        return len(self.requests)

    def _create(self, **kwargs: Any) -> Iterator[Any]:
        for param in self._reject:
            if param in kwargs:
                raise ValueError(f"unsupported parameter: {param}")
        if not self._script:
            raise ScriptExhausted(
                f"model was called a {len(self.requests) + 1}th time but the script has no more steps"
            )
        self.requests.append({"kwargs": dict(kwargs), "n_messages": len(kwargs["messages"])})
        step = self._script.pop(0)
        return _chunks_for(step, len(self.requests))
