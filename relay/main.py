"""Application entry point: bootstrap state and run uvicorn."""

from __future__ import annotations

import sys
import threading
import webbrowser

import uvicorn

from relay.api.app import create_app
from relay.config import APP_HOST, APP_PORT, MAX_TOKENS
from relay.logging import ensure_log_dir
from relay.project.root import load_project_root
from relay.state import create_app_state


def main() -> None:
    try:
        state = create_app_state()
    except RuntimeError as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        sys.exit(1)

    saved_project = load_project_root()
    if saved_project is not None:
        state.project_root = saved_project
        state.shell_cwd = saved_project
    app = create_app(state)
    provider = state.provider
    print(f"LLM provider: {provider.label} ({provider.id})")
    print(f"API base URL: {provider.base_url}")
    print(f"Using model: {provider.model_id}")
    if not provider.local:
        print("Warning: messages and tool output are sent to an external API.")
    print(f"Max tokens per round: {MAX_TOKENS}")
    print(f"Shell starting cwd: {state.shell_cwd}")
    if state.project_root is not None:
        print(f"Project: {state.project_root}")
    print(f"Model logs directory: {ensure_log_dir()}")
    print(f"UI: http://{APP_HOST}:{APP_PORT}")

    url = f"http://{APP_HOST}:{APP_PORT}"
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=APP_HOST, port=APP_PORT, log_level="info")
