"""LLM provider configuration."""

from __future__ import annotations

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
    completion_tokens_param: CompletionTokensParam = "max_tokens"
    extra_completion_kwargs: dict[str, Any] = field(default_factory=dict)
