"""Local chat app backed by LM Studio's OpenAI-compatible server.

Features:
  - Streaming responses
  - Stop button to cancel an in-flight generation (like ChatGPT)
  - Tool calling (function calling) with a multi-round loop
  - DuckDuckGo web_search + fetch_url for grounded live lookups
  - Agent Skills (reusable task procedures; list_skills, read_skill, inspect_page)
  - Tailwind CDN web UI via FastAPI
  - Auto-detects whichever model is currently loaded in LM Studio

Run:
    pip install -r requirements.txt
    pip install -r requirements-web.txt          # optional: web_search, fetch_url
    pip install -r requirements-browser.txt      # optional: inspect_page
    playwright install chromium                  # if using inspect_page
    python relay.py
    python -m relay
    # open http://127.0.0.1:7860

Environment overrides (all optional):
    LLM_PROVIDER            lm_studio (default), openai, anthropic, google, or unsloth
    LM_STUDIO_BASE_URL      default: http://localhost:1234/v1
    LM_STUDIO_API_KEY       default: lm-studio  (LM Studio ignores it, but the SDK requires a value)
    LM_STUDIO_MODEL         pin to a specific model id instead of auto-detecting
    OPENAI_API_KEY          required when LLM_PROVIDER=openai
    OPENAI_MODEL            required when LLM_PROVIDER=openai (e.g. gpt-4o)
    OPENAI_BASE_URL         default: https://api.openai.com/v1
    OPENAI_CONTEXT_WINDOW   default: 128000
    ANTHROPIC_API_KEY       required when LLM_PROVIDER=anthropic
    ANTHROPIC_MODEL         required when LLM_PROVIDER=anthropic (e.g. claude-sonnet-5-5)
    ANTHROPIC_BASE_URL      default: https://api.anthropic.com/v1
    ANTHROPIC_CONTEXT_WINDOW default: 200000
    ANTHROPIC_TEMPERATURE   optional; omit for Claude 4.7+ (they reject values below 1)
    ANTHROPIC_WORKSPACE_ID  optional; some multi-workspace keys require it
    GOOGLE_AI_STUDIO_API_KEY required when LLM_PROVIDER=google
    GOOGLE_AI_STUDIO_MODEL  required when LLM_PROVIDER=google (e.g. gemini-3.8-flash)
    GOOGLE_AI_STUDIO_BASE_URL default: https://generativelanguage.googleapis.com/v1beta/openai/
    GOOGLE_AI_STUDIO_CONTEXT_WINDOW default: 1000000
    GOOGLE_AI_STUDIO_TEMPERATURE optional, 0 to 2; omitted by default (model default)
    GOOGLE_AI_STUDIO_REASONING_EFFORT optional: none, minimal, low, medium, high
    LM_STUDIO_MAX_TOKENS    max completion tokens per round (default: 32768)
    LM_STUDIO_TEMPERATURE   sampling temperature (default: 0.3; lower = more grounded)
    LM_STUDIO_SKILLS_DIRS   extra skill directories (OS path separator; optional)

Per-chat model logs (raw content, tool calls, finish_reason, usage):
    ~/.relay_logs/chat_<session_id>.log
"""

from relay.main import main

if __name__ == "__main__":
    main()
