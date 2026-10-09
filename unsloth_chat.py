"""Local chat app backed by an Unsloth-served OpenAI-compatible endpoint.

Unsloth is a training/inference library, not a chat server. This launcher talks
to whatever OpenAI-compatible process is serving a Unsloth model — typically
vLLM (port 8000), llama-server (port 8001), or SGLang.

Features (same as lm_studio_chat.py):
  - Streaming responses
  - Stop button to cancel an in-flight generation
  - Tool calling with a multi-round loop
  - DuckDuckGo web_search + fetch_url
  - Agent Skills (list_skills, read_skill, inspect_page)
  - Tailwind CDN web UI via FastAPI
  - Auto-detects the model currently loaded on the Unsloth endpoint

Run:
    pip install -r requirements.txt
    pip install -r requirements-web.txt          # optional: web_search, fetch_url
    pip install -r requirements-browser.txt      # optional: inspect_page
    playwright install chromium                  # if using inspect_page

    # Terminal 1 — serve a Unsloth model (vLLM example):
    vllm serve unsloth/Llama-3.2-1B-Instruct

    # or llama-server (set UNSLOTH_BASE_URL=http://127.0.0.1:8001/v1):
    # llama-server --model your-unsloth.gguf --port 8001 --jinja

    # Terminal 2
    python unsloth_chat.py
    # open http://127.0.0.1:7860

Environment overrides (all optional):
    UNSLOTH_BASE_URL        default: http://127.0.0.1:8000/v1
    UNSLOTH_API_KEY         default: sk-no-key-required
    UNSLOTH_MODEL           pin to a specific model id instead of auto-detecting
    LM_STUDIO_MAX_TOKENS    max completion tokens per round (default: 32768)
    LM_STUDIO_TEMPERATURE   sampling temperature (default: 0.3)
    LM_STUDIO_SKILLS_DIRS   extra skill directories (OS path separator; optional)

Per-chat model logs:
    ~/.lm_studio_chat_logs/chat_<session_id>.log
"""

from __future__ import annotations

import os

os.environ["LLM_PROVIDER"] = "unsloth"

from lm_studio_chat.main import main

if __name__ == "__main__":
    main()
