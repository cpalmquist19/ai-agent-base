"""OpenAI cloud model provider."""

from __future__ import annotations

import os

from openai import OpenAI

from lm_studio_chat.providers.base import LLMProvider


def create_openai_provider() -> LLMProvider:
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
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
        completion_tokens_param="max_completion_tokens",
        extra_completion_kwargs=extra_kwargs,
    )
