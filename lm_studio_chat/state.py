"""Mutable application state (replaces module-level globals)."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import OpenAI

from lm_studio_chat.providers import LLMProvider, create_provider


def _close_llm_stream(stream: Any) -> None:
    close = getattr(stream, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


@dataclass
class AppState:
    provider: LLMProvider
    shell_cwd: Path
    project_root: Path | None
    cancel: threading.Event
    session_usage: dict[str, dict[str, Any]]
    sessions_lock: threading.Lock
    context_window: int | None = None
    active_command_lock: threading.Lock = field(default_factory=threading.Lock)
    active_command_proc: subprocess.Popen[str] | None = None
    active_llm_stream_lock: threading.Lock = field(default_factory=threading.Lock)
    active_llm_stream: Any | None = None

    @property
    def client(self) -> OpenAI:
        return self.provider.client

    @property
    def model_id(self) -> str | None:
        return self.provider.model_id


def register_active_llm_stream(state: AppState, stream: Any) -> None:
    with state.active_llm_stream_lock:
        state.active_llm_stream = stream


def clear_active_llm_stream(state: AppState, stream: Any) -> None:
    with state.active_llm_stream_lock:
        if state.active_llm_stream is stream:
            state.active_llm_stream = None


def close_active_llm_stream(state: AppState) -> None:
    with state.active_llm_stream_lock:
        stream = state.active_llm_stream
    if stream is not None:
        _close_llm_stream(stream)


@dataclass
class ToolContext:
    state: AppState
    session_id: str | None = None


def create_app_state(
    *,
    provider: LLMProvider | None = None,
    shell_cwd: Path | None = None,
    project_root: Path | None = None,
) -> AppState:
    cwd = shell_cwd or project_root or Path.cwd()
    return AppState(
        provider=provider or create_provider(),
        shell_cwd=cwd,
        project_root=project_root,
        cancel=threading.Event(),
        session_usage={},
        sessions_lock=threading.Lock(),
    )
