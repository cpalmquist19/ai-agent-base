"""LLM provider configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

from openai import OpenAI

CompletionTokensParam = Literal["max_tokens", "max_completion_tokens"]


@dataclass(frozen=True)
class LLMProvider:
    id: str
    label: str
    client: OpenAI
    model_id: str
    base_url: str
    stream_usage: bool
    local: bool
    supports_vision: bool = False
    completion_tokens_param: CompletionTokensParam = "max_tokens"
    extra_completion_kwargs: dict[str, Any] = field(default_factory=dict)
    # Fallback input window when the provider has no runtime telemetry.
    context_window: int | None = None
    # Claude 4.7+ rejects temperature below 1; omit it and use the model default.
    omit_temperature: bool = False
    # When set, overrides the global LM_STUDIO_TEMPERATURE for this provider.
    temperature: float | None = None


def positive_int_env(name: str, default: int) -> int:
    """Read a positive integer environment variable, or ``default`` when unset."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer.") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be a positive integer.")
    return value
