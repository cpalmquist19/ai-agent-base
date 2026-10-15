"""Google AI Studio (Gemini) provider via the OpenAI-compatible endpoint.

Gemini is called with the OpenAI SDK against
``https://generativelanguage.googleapis.com/v1beta/openai/``, so streaming, tool
calls, and the chat engine stay the same as the other providers. Google documents
this layer as beta; native Gemini features (grounding, code execution, the
``google-genai`` SDK's file API) are not exposed here.
"""

from __future__ import annotations

import os

from openai import OpenAI

from relay.providers.base import LLMProvider, positive_int_env

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
# Current Gemini models take about a million input tokens. Lower
# GOOGLE_AI_STUDIO_CONTEXT_WINDOW to keep requests (and cost) smaller, or for
# Gemma models, which have far smaller windows.
_DEFAULT_CONTEXT_WINDOW = 1_000_000
_REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high")


def google_model_supports_vision(model_id: str) -> bool:
    return "gemini" in model_id.lower()


def _optional_temperature() -> tuple[bool, float | None]:
    """Return ``(omit_temperature, temperature)``.

    Google recommends the model default (1.0) for current Gemini models, and
    lower values can cause looping, so temperature is omitted unless
    ``GOOGLE_AI_STUDIO_TEMPERATURE`` is set.
    """
    raw = os.getenv("GOOGLE_AI_STUDIO_TEMPERATURE", "").strip()
    if not raw:
        return True, None
    try:
        temperature = float(raw)
    except ValueError as exc:
        raise RuntimeError(
            "GOOGLE_AI_STUDIO_TEMPERATURE must be a number between 0 and 2."
        ) from exc
    if not 0 <= temperature <= 2:
        raise RuntimeError("GOOGLE_AI_STUDIO_TEMPERATURE must be between 0 and 2.")
    return False, temperature


def _reasoning_kwargs() -> dict[str, object]:
    """``reasoning_effort`` is sent only when asked for.

    Gemini maps it to a thinking level or budget. ``none`` disables thinking on
    2.5 Flash only; Gemini 2.5 Pro and 3 models always think.
    """
    effort = os.getenv("GOOGLE_AI_STUDIO_REASONING_EFFORT", "").strip().lower()
    if not effort:
        return {}
    if effort not in _REASONING_EFFORTS:
        raise RuntimeError(
            "GOOGLE_AI_STUDIO_REASONING_EFFORT must be one of: "
            + ", ".join(_REASONING_EFFORTS)
        )
    return {"reasoning_effort": effort}


def create_google_provider() -> LLMProvider:
    api_key = os.getenv("GOOGLE_AI_STUDIO_API_KEY", "").strip()
    model = os.getenv("GOOGLE_AI_STUDIO_MODEL", "").strip()
    base_url = os.getenv("GOOGLE_AI_STUDIO_BASE_URL", _DEFAULT_BASE_URL).strip()
    if not api_key:
        raise RuntimeError(
            "GOOGLE_AI_STUDIO_API_KEY is required when LLM_PROVIDER=google. "
            "Set it in your environment or .env file."
        )
    if not model:
        raise RuntimeError(
            "GOOGLE_AI_STUDIO_MODEL is required when LLM_PROVIDER=google "
            "(e.g. gemini-3.8-flash)."
        )
    omit_temperature, temperature = _optional_temperature()
    client = OpenAI(base_url=base_url, api_key=api_key)
    return LLMProvider(
        id="google",
        label="Google AI Studio",
        client=client,
        model_id=model,
        base_url=base_url,
        stream_usage=True,
        local=False,
        supports_vision=google_model_supports_vision(model),
        completion_tokens_param="max_tokens",
        extra_completion_kwargs=_reasoning_kwargs(),
        context_window=positive_int_env(
            "GOOGLE_AI_STUDIO_CONTEXT_WINDOW", _DEFAULT_CONTEXT_WINDOW
        ),
        omit_temperature=omit_temperature,
        temperature=temperature,
    )
