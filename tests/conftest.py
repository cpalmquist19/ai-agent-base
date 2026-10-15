"""Shared fixtures: a chat engine wired to a scripted model and a throwaway project folder."""

from __future__ import annotations

from typing import Any

import pytest

from evals.fake import ScriptedClient
from relay.chat.engine import run_chat
from relay.providers.base import LLMProvider
from relay.state import create_app_state


@pytest.fixture(autouse=True)
def _confine_paths(monkeypatch):
    # A developer's .env may switch off path confinement; tests must not depend on it.
    monkeypatch.delenv("LM_STUDIO_ALLOW_UNRESTRICTED_PATHS", raising=False)


@pytest.fixture
def make_state(tmp_path):
    """Return ``(state, client)`` for a scripted model and an empty project root."""

    def _make(
        script=(),
        *,
        stream_usage: bool = False,
        reject_params: tuple[str, ...] = (),
        **provider_kwargs: Any,
    ):
        client = ScriptedClient(list(script), reject_params=reject_params)
        fields: dict[str, Any] = {
            "id": "scripted",
            "label": "Scripted",
            "client": client,
            "model_id": "scripted",
            "base_url": "",
            "stream_usage": stream_usage,
            "local": True,
        }
        fields.update(provider_kwargs)
        provider = LLMProvider(**fields)
        state = create_app_state(provider=provider, project_root=tmp_path)
        return state, client

    return _make


def drive(state, prompt: str = "go", **kwargs: Any):
    """Run one user turn to completion; return ``(final_partial, messages)``."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "test system prompt"},
        {"role": "user", "content": prompt},
    ]
    final = None
    for partial in run_chat(state, "scripted", messages, **kwargs):
        final = partial
    return final, messages
