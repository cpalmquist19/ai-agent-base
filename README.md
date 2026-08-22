# lm-studio-chat

A local coding agent with a web UI, backed by [LM Studio](https://lmstudio.ai/)'s OpenAI-compatible API.

Stream chat responses, cancel in-flight generations, and let the model use tools — file I/O, shell commands, web search, optional browser inspection, and reusable **Agent Skills**.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Features

- Streaming chat with stop/cancel support
- Tool calling with a multi-round loop (read/write files, shell, web, skills)
- Project folder explorer with drag-and-drop attachments
- Vision-capable models: image attachments in chat
- Agent Skills: reusable task procedures in `skills/*/SKILL.md`
- Auto-detects the model loaded in LM Studio
- Binds to `127.0.0.1` by default — local use only

## Prerequisites

- Python 3.10 or newer
- [LM Studio](https://lmstudio.ai/) running with a model loaded and the local server enabled (default `http://localhost:1234`)

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/lm-studio-chat.git
cd lm-studio-chat

python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt

# Optional: web search + URL fetch
pip install -r requirements-web.txt

# Optional: browser page inspection
pip install -r requirements-browser.txt
playwright install chromium

python lm_studio_chat.py
# or: python -m lm_studio_chat
```

Open **http://127.0.0.1:7860** in your browser.

## Configuration

Set environment variables in `.env` (loaded automatically) or export them before starting (see [`.env.example`](.env.example)):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `lm_studio` | `lm_studio` (local) or `openai` (cloud) |
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | LM Studio API base URL |
| `LM_STUDIO_API_KEY` | `lm-studio` | API key (LM Studio ignores it; SDK requires a value) |
| `LM_STUDIO_MODEL` | *(auto-detect)* | Pin a specific model id |
| `OPENAI_API_KEY` | — | **Required** when `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | — | **Required** when `LLM_PROVIDER=openai` (e.g. `gpt-4o`) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API base URL |
| `LM_STUDIO_MAX_TOKENS` | `32768` | Max completion tokens per round |
| `LM_STUDIO_TEMPERATURE` | `0.3` | Sampling temperature |
| `LM_STUDIO_CHAT_HOST` | `127.0.0.1` | UI bind address |
| `LM_STUDIO_CHAT_PORT` | `7860` | UI port |
| `LM_STUDIO_SKILLS_DIRS` | — | Extra skill directories (`;` on Windows, `:` on Unix) |
| `LM_STUDIO_INSPECT_PAGE_HEADED` | — | Set `1`/`true` to show Playwright browser window |

Session logs are written to `~/.lm_studio_chat_logs/chat_<session_id>.log`.

### Using OpenAI instead of LM Studio

```bash
set LLM_PROVIDER=openai
set OPENAI_API_KEY=sk-...
set OPENAI_MODEL=gpt-4o
python lm_studio_chat.py
```

Messages and tool output are sent to OpenAI's API. Shell/file tools still run locally — use with care.

## Agent Skills

Skills are markdown files with YAML frontmatter:

```
skills/
  example/
    SKILL.md
```

Each skill needs at least `name` and `description` in frontmatter. The model can call `list_skills()` and `read_skill(name)` to load instructions. See [`skills/example/SKILL.md`](skills/example/SKILL.md).

## Security

**This is a local development agent with real power.**

- The model can run **shell commands** and **read/write files** on your machine (within the working directory / project you open).
- The server has **no authentication**. Keep `LM_STUDIO_CHAT_HOST=127.0.0.1` — do **not** expose it to the network.
- Do not run against untrusted prompts on a machine with sensitive data unless you understand the risk.
- With `LLM_PROVIDER=openai`, chat content is sent to OpenAI; local tools still execute on your machine.

## Project layout

```
lm_studio_chat/     Python package (API, chat engine, tools)
static/             Web UI (HTML + JS)
skills/             Bundled agent skills
lm_studio_chat.py   Backward-compatible entry shim
```

## Development

```bash
pip install -r requirements-web.txt -r requirements-browser.txt
playwright install chromium
python lm_studio_chat.py
```

Internal refactor notes: [`docs/REFACTOR_PLAN.md`](docs/REFACTOR_PLAN.md), [`docs/MULTI_PROVIDER_PLAN.md`](docs/MULTI_PROVIDER_PLAN.md).

## License

[MIT](LICENSE)
