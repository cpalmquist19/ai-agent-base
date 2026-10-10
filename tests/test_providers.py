"""Provider factory: OpenAI and Anthropic configuration, without network calls."""

from __future__ import annotations

import pytest

from lm_studio_chat.providers.factory import create_provider
from lm_studio_chat.providers.openai_provider import openai_model_supports_vision


def _cloud(monkeypatch, provider: str, **env: str) -> None:
    monkeypatch.setenv("LLM_PROVIDER", provider)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_openai_requires_api_key(monkeypatch):
    _cloud(monkeypatch, "openai", OPENAI_MODEL="gpt-4o")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        create_provider()


def test_openai_requires_model(monkeypatch):
    _cloud(monkeypatch, "openai", OPENAI_API_KEY="sk-test")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_MODEL"):
        create_provider()


def test_openai_provider_uses_chat_completions_settings(monkeypatch):
    _cloud(
        monkeypatch,
        "openai",
        OPENAI_API_KEY="sk-test",
        OPENAI_MODEL="gpt-4o",
        OPENAI_BASE_URL="https://api.openai.com/v1",
    )
    monkeypatch.delenv("OPENAI_CONTEXT_WINDOW", raising=False)
    provider = create_provider()
    assert provider.id == "openai"
    assert provider.label == "OpenAI"
    assert provider.model_id == "gpt-4o"
    assert provider.local is False
    assert provider.supports_vision is True
    assert provider.completion_tokens_param == "max_completion_tokens"
    assert provider.context_window == 128_000
    assert provider.omit_temperature is False
    assert provider.base_url == "https://api.openai.com/v1"


def test_openai_context_window_override(monkeypatch):
    _cloud(
        monkeypatch,
        "openai",
        OPENAI_API_KEY="sk-test",
        OPENAI_MODEL="gpt-4.1",
        OPENAI_CONTEXT_WINDOW="1000000",
    )
    assert create_provider().context_window == 1_000_000


def test_openai_vision_markers():
    assert openai_model_supports_vision("gpt-5")
    assert openai_model_supports_vision("gpt-4o-mini")
    assert not openai_model_supports_vision("gpt-3.5-turbo")


def test_anthropic_requires_api_key(monkeypatch):
    _cloud(monkeypatch, "anthropic", ANTHROPIC_MODEL="claude-sonnet-5-5")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        create_provider()


def test_anthropic_requires_model(monkeypatch):
    _cloud(monkeypatch, "anthropic", ANTHROPIC_API_KEY="sk-ant-test")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_MODEL"):
        create_provider()


def test_anthropic_provider_omits_temperature_by_default(monkeypatch):
    _cloud(
        monkeypatch,
        "anthropic",
        ANTHROPIC_API_KEY="sk-ant-test",
        ANTHROPIC_MODEL="claude-sonnet-5-5",
        ANTHROPIC_BASE_URL="https://api.anthropic.com/v1",
    )
    monkeypatch.delenv("ANTHROPIC_TEMPERATURE", raising=False)
    monkeypatch.delenv("ANTHROPIC_CONTEXT_WINDOW", raising=False)
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    provider = create_provider()
    assert provider.id == "anthropic"
    assert provider.label == "Anthropic"
    assert provider.model_id == "claude-sonnet-5-5"
    assert provider.local is False
    assert provider.supports_vision is True
    assert provider.stream_usage is True
    assert provider.completion_tokens_param == "max_tokens"
    assert provider.context_window == 200_000
    assert provider.omit_temperature is True
    assert provider.temperature is None
    assert provider.base_url == "https://api.anthropic.com/v1"


def test_anthropic_temperature_and_workspace(monkeypatch):
    _cloud(
        monkeypatch,
        "anthropic",
        ANTHROPIC_API_KEY="sk-ant-test",
        ANTHROPIC_MODEL="claude-3-5-haiku-latest",
        ANTHROPIC_TEMPERATURE="0.4",
        ANTHROPIC_WORKSPACE_ID="wrkspc_123",
        ANTHROPIC_CONTEXT_WINDOW="1000000",
    )
    provider = create_provider()
    assert provider.omit_temperature is False
    assert provider.temperature == 0.4
    assert provider.context_window == 1_000_000
    assert provider.client.default_headers["anthropic-workspace-id"] == "wrkspc_123"


def test_anthropic_rejects_temperature_below_zero(monkeypatch):
    _cloud(
        monkeypatch,
        "anthropic",
        ANTHROPIC_API_KEY="sk-ant-test",
        ANTHROPIC_MODEL="claude-sonnet-5-5",
        ANTHROPIC_TEMPERATURE="1.5",
    )
    with pytest.raises(RuntimeError, match="ANTHROPIC_TEMPERATURE"):
        create_provider()


def test_google_requires_api_key(monkeypatch):
    _cloud(monkeypatch, "google", GOOGLE_AI_STUDIO_MODEL="gemini-3.8-flash")
    monkeypatch.delenv("GOOGLE_AI_STUDIO_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_AI_STUDIO_API_KEY"):
        create_provider()


def test_google_requires_model(monkeypatch):
    _cloud(monkeypatch, "google", GOOGLE_AI_STUDIO_API_KEY="key-test")
    monkeypatch.delenv("GOOGLE_AI_STUDIO_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_AI_STUDIO_MODEL"):
        create_provider()


def test_google_provider_defaults(monkeypatch):
    _cloud(
        monkeypatch,
        "google",
        GOOGLE_AI_STUDIO_API_KEY="key-test",
        GOOGLE_AI_STUDIO_MODEL="gemini-3.8-flash",
    )
    for name in (
        "GOOGLE_AI_STUDIO_BASE_URL",
        "GOOGLE_AI_STUDIO_CONTEXT_WINDOW",
        "GOOGLE_AI_STUDIO_TEMPERATURE",
        "GOOGLE_AI_STUDIO_REASONING_EFFORT",
    ):
        monkeypatch.delenv(name, raising=False)
    provider = create_provider()
    assert provider.id == "google"
    assert provider.label == "Google AI Studio"
    assert provider.model_id == "gemini-3.8-flash"
    assert provider.local is False
    assert provider.supports_vision is True
    assert provider.stream_usage is True
    assert provider.completion_tokens_param == "max_tokens"
    assert provider.context_window == 1_000_000
    assert provider.omit_temperature is True
    assert provider.temperature is None
    assert provider.extra_completion_kwargs == {}
    assert provider.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"


def test_google_temperature_reasoning_and_context_overrides(monkeypatch):
    _cloud(
        monkeypatch,
        "google",
        GOOGLE_AI_STUDIO_API_KEY="key-test",
        GOOGLE_AI_STUDIO_MODEL="gemini-3.8-flash",
        GOOGLE_AI_STUDIO_TEMPERATURE="0.4",
        GOOGLE_AI_STUDIO_REASONING_EFFORT="Low",
        GOOGLE_AI_STUDIO_CONTEXT_WINDOW="200000",
    )
    provider = create_provider()
    assert provider.omit_temperature is False
    assert provider.temperature == 0.4
    assert provider.extra_completion_kwargs == {"reasoning_effort": "low"}
    assert provider.context_window == 200_000


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GOOGLE_AI_STUDIO_TEMPERATURE", "2.5"),
        ("GOOGLE_AI_STUDIO_TEMPERATURE", "hot"),
        ("GOOGLE_AI_STUDIO_REASONING_EFFORT", "extreme"),
    ],
)
def test_google_rejects_bad_settings(monkeypatch, name, value):
    _cloud(
        monkeypatch,
        "google",
        GOOGLE_AI_STUDIO_API_KEY="key-test",
        GOOGLE_AI_STUDIO_MODEL="gemini-3.8-flash",
        **{name: value},
    )
    with pytest.raises(RuntimeError, match=name):
        create_provider()


def test_unknown_provider_names_the_supported_set(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "chatgpt")
    with pytest.raises(RuntimeError, match="anthropic"):
        create_provider()
