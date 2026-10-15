"""Create the configured LLM provider from environment."""

from __future__ import annotations

import os

from relay.providers.anthropic import create_anthropic_provider
from relay.providers.base import LLMProvider
from relay.providers.google import create_google_provider
from relay.providers.lm_studio import create_lm_studio_provider
from relay.providers.openai_provider import create_openai_provider
from relay.providers.unsloth import create_unsloth_provider

_PROVIDERS = {
    "lm_studio": create_lm_studio_provider,
    "openai": create_openai_provider,
    "anthropic": create_anthropic_provider,
    "google": create_google_provider,
    "unsloth": create_unsloth_provider,
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
