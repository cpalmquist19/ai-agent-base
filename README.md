# lm-studio-chat

A local coding agent with a web UI, backed by [LM Studio](https://lmstudio.ai/)'s OpenAI-compatible API.

Stream chat responses, cancel in-flight generations, and let the model use tools — file I/O, shell commands, web search, optional browser inspection, and reusable **Agent Skills**.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Features

- Streaming chat with stop/cancel support
- Tool calling with a multi-round loop (read/write files, shell, web, skills)
- Project folder explorer with drag-and-drop attachments
- Image attachments (when the loaded model supports vision)
- Agent Skills: reusable task procedures in `skills/*/SKILL.md`
- Auto-detects the model loaded in LM Studio
- Binds to `127.0.0.1` by default — local use only

## Prerequisites

- Python 3.10 or newer
- [LM Studio](https://lmstudio.ai/) running with a model loaded and the local server enabled (default `http://localhost:1234`)

## Quick start

```bash
git clone https://github.com/cpalmquist19/ai-agent-base.git
cd ai-agent-base

python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt

# Optional: web search (UI lists web_search as unavailable until installed)
pip install -r requirements-web.txt

# Optional: browser page inspection (UI lists inspect_page as unavailable until installed)
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
| `LLM_PROVIDER` | `lm_studio` | `lm_studio` (local), `openai` (ChatGPT), `anthropic` (Claude), or `unsloth` (local OpenAI-compatible server) |
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | LM Studio API base URL |
| `LM_STUDIO_API_KEY` | `lm-studio` | API key (LM Studio ignores it; SDK requires a value) |
| `LM_STUDIO_MODEL` | *(auto-detect)* | Pin a specific model id |
| `OPENAI_API_KEY` | — | **Required** when `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | — | **Required** when `LLM_PROVIDER=openai` (e.g. `gpt-4o`) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API base URL |
| `OPENAI_CONTEXT_WINDOW` | `128000` | Input-token budget used to trim history |
| `ANTHROPIC_API_KEY` | — | **Required** when `LLM_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL` | — | **Required** when `LLM_PROVIDER=anthropic` (e.g. `claude-sonnet-5-5`) |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com/v1` | Anthropic OpenAI-compatible API base URL |
| `ANTHROPIC_CONTEXT_WINDOW` | `200000` | Input-token budget used to trim history (raise for 1M-context models) |
| `ANTHROPIC_TEMPERATURE` | *(unset)* | Optional, 0 to 1. Leave unset for Claude 4.7 and later |
| `ANTHROPIC_WORKSPACE_ID` | — | Optional workspace header for some multi-workspace keys |
| `UNSLOTH_BASE_URL` | `http://127.0.0.1:8000/v1` | Unsloth OpenAI-compatible endpoint (vLLM default) |
| `UNSLOTH_API_KEY` | `sk-no-key-required` | API key (ignored by most local servers; SDK requires a value) |
| `UNSLOTH_MODEL` | *(auto-detect)* | Pin a specific Unsloth model id |
| `LM_STUDIO_MAX_TOKENS` | `32768` | Max completion tokens per round |
| `LM_STUDIO_TEMPERATURE` | `0.3` | Sampling temperature |
| `LM_STUDIO_CHAT_HOST` | `127.0.0.1` | UI bind address |
| `LM_STUDIO_CHAT_PORT` | `7860` | UI port |
| `LM_STUDIO_SKILLS_DIRS` | — | Extra skill directories (`;` on Windows, `:` on Unix) |
| `LM_STUDIO_INSPECT_PAGE_HEADED` | — | Set `1`/`true` to show Playwright browser window |
| `LM_STUDIO_ALLOW_UNRESTRICTED_PATHS` | — | Set `1`/`true` to disable project path confinement for file tools and `cd` |

Session logs are written to `~/.lm_studio_chat_logs/chat_<session_id>.log`.

### Using OpenAI instead of LM Studio

```bash
set LLM_PROVIDER=openai
set OPENAI_API_KEY=sk-...
set OPENAI_MODEL=gpt-4o
python lm_studio_chat.py
```

Messages and tool output are sent to OpenAI's API. Shell/file tools still run locally — use with care.

### Using Claude instead of LM Studio

Claude is called through [Anthropic's OpenAI-compatible endpoint](https://platform.claude.com/docs/en/api/openai-sdk), so the same tool loop and streaming path are used.

```bash
set LLM_PROVIDER=anthropic
set ANTHROPIC_API_KEY=sk-ant-...
set ANTHROPIC_MODEL=claude-sonnet-5-5
python lm_studio_chat.py
```

Other current model ids include `claude-opus-5-5` and `claude-haiku-5-5`. Claude 4.7 and later reject a temperature below 1, so temperature is omitted unless you set `ANTHROPIC_TEMPERATURE` (useful for older Claude models). Messages and tool output are sent to Anthropic. Shell/file tools still run locally.

### Using Unsloth instead of LM Studio

Unsloth is not a chat server. Serve a Unsloth model with an OpenAI-compatible process, then run this app against it.

```bash
# Terminal 1 — vLLM (default port 8000)
vllm serve unsloth/Llama-3.2-1B-Instruct

# Terminal 2
python unsloth_chat.py
```

For llama-server (typical port 8001):

```bash
llama-server --model your-unsloth.gguf --port 8001 --jinja
set UNSLOTH_BASE_URL=http://127.0.0.1:8001/v1
python unsloth_chat.py
```

You can also set `LLM_PROVIDER=unsloth` and run `python lm_studio_chat.py`. Tool calling needs a server that supports OpenAI tools (vLLM/SGLang, or llama-server with `--jinja`).

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

- **File tools are project-scoped by default:** `read_file`, `write_file`, `str_replace`, `search_file`, and `list_dir` are restricted to the open project (or initial working directory). Attempts to access paths outside the sandbox are rejected. To disable this restriction, set `LM_STUDIO_ALLOW_UNRESTRICTED_PATHS=1`.
- **Shell commands (`run_command`) are not fully sandboxed:** while bare `cd` is constrained to the sandbox, arbitrary shell commands execute with the permissions of the running process. Treat shell execution with appropriate caution.
- The server has **no authentication**. Keep `LM_STUDIO_CHAT_HOST=127.0.0.1` — do **not** expose it to the network.
- Do not run against untrusted prompts on a machine with sensitive data unless you understand the risk.
- With `LLM_PROVIDER=openai` or `LLM_PROVIDER=anthropic`, chat content is sent to that provider; local tools still execute on your machine.

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
