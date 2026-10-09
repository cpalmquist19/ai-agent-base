"""LM Studio local model provider."""

from __future__ import annotations

import os

from openai import APIConnectionError, OpenAI

from lm_studio_chat.config import LM_STUDIO_API_KEY, LM_STUDIO_BASE_URL
from lm_studio_chat.lm_client import model_supports_vision
from lm_studio_chat.providers.base import LLMProvider


def detect_model_id(client: OpenAI) -> str:
    pinned = os.getenv("LM_STUDIO_MODEL")
    if pinned:
        return pinned
    try:
        models = client.models.list()
    except APIConnectionError as exc:
        raise RuntimeError(
            f"Could not connect to LM Studio at {LM_STUDIO_BASE_URL}. "
            "Start LM Studio and enable the local server, or set "
            "LLM_PROVIDER=openai in your .env to use OpenAI."
        ) from exc
    if not models.data:
        raise RuntimeError(
            "No model is currently loaded in LM Studio. "
            "Open the Developer tab, load a model, and enable the server."
        )
    return models.data[0].id


def create_lm_studio_provider() -> LLMProvider:
    client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key=LM_STUDIO_API_KEY)
    model_id = detect_model_id(client)
    return LLMProvider(
        id="lm_studio",
        label="LM Studio (local)",
        client=client,
        model_id=model_id,
        base_url=LM_STUDIO_BASE_URL,
        stream_usage=True,
        local=True,
        supports_vision=model_supports_vision(model_id),
    )
