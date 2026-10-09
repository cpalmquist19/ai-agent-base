"""Unsloth local model provider (OpenAI-compatible vLLM / SGLang / llama-server)."""

from __future__ import annotations

import os

from openai import APIConnectionError, OpenAI

from lm_studio_chat.config import UNSLOTH_API_KEY, UNSLOTH_BASE_URL
from lm_studio_chat.providers.base import LLMProvider

_VISION_MARKERS = (
    "vision",
    "vlm",
    "llava",
    "pixtral",
    "internvl",
    "-vl-",
    "-vl_",
    "qwen2-vl",
    "qwen2.5-vl",
    "qwen2_5_vl",
    "llama-3.2-vision",
    "llama_3.2_vision",
)


def unsloth_model_supports_vision(model_id: str) -> bool:
    mid = model_id.lower()
    return any(marker in mid for marker in _VISION_MARKERS)


def detect_model_id(client: OpenAI) -> str:
    pinned = os.getenv("UNSLOTH_MODEL", "").strip()
    if pinned:
        return pinned
    try:
        models = client.models.list()
    except APIConnectionError as exc:
        raise RuntimeError(
            f"Could not connect to the Unsloth OpenAI endpoint at {UNSLOTH_BASE_URL}. "
            "Start a server with a Unsloth model (vLLM on :8000, llama-server on :8001, "
            "or SGLang), or set UNSLOTH_BASE_URL."
        ) from exc
    if not models.data:
        raise RuntimeError(
            f"No model is loaded at {UNSLOTH_BASE_URL}. "
            "Serve a Unsloth model (e.g. `vllm serve unsloth/Llama-3.2-1B-Instruct`) "
            "or set UNSLOTH_MODEL."
        )
    return models.data[0].id


def create_unsloth_provider() -> LLMProvider:
    client = OpenAI(base_url=UNSLOTH_BASE_URL, api_key=UNSLOTH_API_KEY)
    model_id = detect_model_id(client)
    return LLMProvider(
        id="unsloth",
        label="Unsloth (local)",
        client=client,
        model_id=model_id,
        base_url=UNSLOTH_BASE_URL,
        stream_usage=True,
        local=True,
        supports_vision=unsloth_model_supports_vision(model_id),
    )
