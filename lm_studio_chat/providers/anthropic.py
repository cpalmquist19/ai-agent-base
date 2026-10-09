"""Anthropic Claude provider via the OpenAI-compatible endpoint.

Claude is called with the OpenAI SDK against ``https://api.anthropic.com/v1/``,
so streaming, tool calls, and the chat engine stay the same as the other
providers. Anthropic documents this layer as fully functional for chat
completions; native Claude features (citations, prompt caching, extended
thinking details) are not exposed here.
"""

from __future__ import annotations

import os

from openai import OpenAI

from lm_studio_chat.providers.base import LLMProvider, positive_int_env

# Safe across Claude 3 (200k) and current 1M-context models. Raise
# ANTHROPIC_CONTEXT_WINDOW when you want the agent to keep more history.
_DEFAULT_CONTEXT_WINDOW = 200_000


def anthropic_model_supports_vision(model_id: str) -> bool:
    return "claude" in model_id.lower()


def _optional_temperature() -> tuple[bool, float | None]:
    """Return ``(omit_temperature, temperature)``.

    Claude 4.7 and later reject any temperature below 1. The app default is
    0.3, so temperature is omitted unless ``ANTHROPIC_TEMPERATURE`` is set.
    """
    raw = os.getenv("ANTHROPIC_TEMPERATURE", "").strip()
    if not raw:
        return True, None
    try:
        temperature = float(raw)
    except ValueError as exc:
        raise RuntimeError(
            "ANTHROPIC_TEMPERATURE must be a number between 0 and 1."
        ) from exc
    if not 0 <= temperature <= 1:
        raise RuntimeError(
            "ANTHROPIC_TEMPERATURE must be between 0 and 1. "
            "Claude 4.7 and later reject any temperature below 1; "
            "leave the variable unset to use the model default."
        )
    return False, temperature


def create_anthropic_provider() -> LLMProvider:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    model = os.getenv("ANTHROPIC_MODEL", "").strip()
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").strip()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic. "
            "Set it in your environment or .env file."
        )
    if not model:
        raise RuntimeError(
            "ANTHROPIC_MODEL is required when LLM_PROVIDER=anthropic "
            "(e.g. claude-sonnet-5-5, claude-opus-5-5, claude-haiku-5-5)."
        )
    omit_temperature, temperature = _optional_temperature()
    headers: dict[str, str] = {}
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
    if workspace:
        headers["anthropic-workspace-id"] = workspace
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        default_headers=headers or None,
    )
    return LLMProvider(
        id="anthropic",
        label="Anthropic",
        client=client,
        model_id=model,
        base_url=base_url,
        stream_usage=True,
        local=False,
        supports_vision=anthropic_model_supports_vision(model),
        completion_tokens_param="max_tokens",
        context_window=positive_int_env(
            "ANTHROPIC_CONTEXT_WINDOW", _DEFAULT_CONTEXT_WINDOW
        ),
        omit_temperature=omit_temperature,
        temperature=temperature,
    )
