"""OpenAI cloud model provider."""

from __future__ import annotations

import os

from openai import OpenAI

from relay.providers.base import LLMProvider, positive_int_env

# GPT-4o / GPT-4.1 class windows. Raise OPENAI_CONTEXT_WINDOW for larger models.
_DEFAULT_CONTEXT_WINDOW = 128_000


def openai_model_supports_vision(model_id: str) -> bool:
    mid = model_id.lower()
    return any(p in mid for p in ("gpt-4o", "gpt-4.1", "gpt-5", "o4", "vision"))


def create_openai_provider() -> LLMProvider:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required when LLM_PROVIDER=openai. "
            "Set it in your environment or .env file."
        )
    if not model:
        raise RuntimeError(
            "OPENAI_MODEL is required when LLM_PROVIDER=openai "
            "(e.g. gpt-4o, gpt-4o-mini)."
        )
    client = OpenAI(base_url=base_url, api_key=api_key)
    reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "none").strip()
    extra_kwargs: dict[str, object] = {}
    if reasoning_effort:
        extra_kwargs["reasoning_effort"] = reasoning_effort
    return LLMProvider(
        id="openai",
        label="OpenAI",
        client=client,
        model_id=model,
        base_url=base_url,
        stream_usage=True,
        local=False,
        supports_vision=openai_model_supports_vision(model),
        completion_tokens_param="max_completion_tokens",
        extra_completion_kwargs=extra_kwargs,
        context_window=positive_int_env("OPENAI_CONTEXT_WINDOW", _DEFAULT_CONTEXT_WINDOW),
    )
