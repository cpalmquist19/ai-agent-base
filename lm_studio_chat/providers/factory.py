"""Create the configured LLM provider from environment."""

from __future__ import annotations

import os

from lm_studio_chat.providers.base import LLMProvider
from lm_studio_chat.providers.lm_studio import create_lm_studio_provider
from lm_studio_chat.providers.openai_provider import create_openai_provider

_PROVIDERS = {
    "lm_studio": create_lm_studio_provider,
    "openai": create_openai_provider,
}


def create_provider() -> LLMProvider:
    provider_id = os.getenv("LLM_PROVIDER", "lm_studio").strip().lower()
    factory = _PROVIDERS.get(provider_id)
    if factory is None:
        supported = ", ".join(sorted(_PROVIDERS))
        raise RuntimeError(
            f"Unknown LLM_PROVIDER={provider_id!r}. Supported: {supported}"
        )
    return factory()
