# Relay

A local coding agent with a web UI. Run it against a model in [LM Studio](https://lmstudio.ai/) on your own machine, or point it at OpenAI, Anthropic (Claude), Google Gemini, or a local Unsloth server.

Relay streams chat responses and lets the model work in your project: it can read, write and search files, run shell commands, search the web, and inspect pages in a headless browser. It also loads reusable **Agent Skills**.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Features

- **Tool use:** the model can read, write and search project files, run shell commands, fetch web pages, and inspect pages in a headless browser.
- **Project explorer:** open a folder, browse it, and drag files into the chat as attachments.
- **Streaming with stop:** responses stream in, and you can cancel a generation at any time.
- **Images:** attach images when the loaded model supports vision.
- **Agent Skills:** reusable task procedures written as `SKILL.md` files.
- **Local or hosted models:** LM Studio and Unsloth run on your machine; OpenAI, Anthropic and Google are selected with one setting.
- **Local by default:** the server binds to `127.0.0.1`. With a local provider, chat content stays on your machine.

## Quick start

You need Python 3.10 or newer, and [LM Studio](https://lmstudio.ai/) with a model loaded and its local server running (default `http://localhost:1234`).

```bash
git clone https://github.com/cpalmquist19/relay.git
cd relay

python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
python relay.py
```

Open **http://127.0.0.1:7860**. Relay detects the model loaded in LM Studio automatically.

### Optional tools

Some tools need extra packages. The UI lists a tool as unavailable until its packages are installed.

```bash
# web_search and fetch_url
pip install -r requirements-web.txt

# inspect_page (headless browser)
pip install -r requirements-browser.txt
playwright install chromium
```

## Security

Relay is a development agent with real power, and it has no login. It is meant for one user on their own machine.

- **File tools stay in the project folder.** `read_file`, `write_file`, `str_replace`, `search_file` and `list_dir` reject paths outside the open project (or the starting directory). Set `LM_STUDIO_ALLOW_UNRESTRICTED_PATHS=1` to lift this.
- **Shell commands are not sandboxed.** `run_command` runs with your user's permissions. A bare `cd` is confined to the project, but other commands can reach any file you can.
- **Keep the server on localhost.** The server has no authentication. Leave `RELAY_HOST=127.0.0.1` and do not expose it to a network.
- **Hosted providers receive your chat.** With `openai`, `anthropic` or `google`, messages and tool output go to that provider. Local tools still run on your machine.
- **Untrusted content can steer the model.** Web pages and files can contain instructions the model may follow, including shell commands. Review what the agent does before using Relay on sensitive work.

## Using other providers

Set `LLM_PROVIDER` and the provider's key and model, either in a `.env` file in the project folder (copy [`.env.example`](.env.example)) or in your shell.

| Provider | `LLM_PROVIDER` | Required settings |
|----------|----------------|-------------------|
| LM Studio (default, local) | `lm_studio` | None, beyond LM Studio running with a model loaded |
| OpenAI | `openai` | `OPENAI_API_KEY`, `OPENAI_MODEL` (e.g. `gpt-4o`) |
| Anthropic (Claude) | `anthropic` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (e.g. `claude-sonnet-5-5`) |
| Google (Gemini via AI Studio) | `google` | `GOOGLE_AI_STUDIO_API_KEY`, `GOOGLE_AI_STUDIO_MODEL` (e.g. `gemini-3.8-flash`) |
| Unsloth (local OpenAI-compatible server) | `unsloth` | A running server, and `UNSLOTH_BASE_URL` if it isn't on the default port |

```bash
set LLM_PROVIDER=anthropic
set ANTHROPIC_API_KEY=sk-ant-...
set ANTHROPIC_MODEL=claude-sonnet-5-5
python relay.py
```

`set` is the Windows command prompt syntax. In PowerShell use `$env:LLM_PROVIDER="anthropic"`, and on macOS/Linux use `export`.

Provider notes:

- **Claude** is called through [Anthropic's OpenAI-compatible endpoint](https://platform.claude.com/docs/en/api/openai-sdk), so the same tool loop and streaming are used. Claude 4.7 and later reject a temperature below 1, so Relay omits temperature unless you set `ANTHROPIC_TEMPERATURE`. Other current model ids include `claude-opus-5-5` and `claude-haiku-5-5`.
- **Gemini** is called through [Google's OpenAI-compatible endpoint](https://ai.google.dev/gemini-api/docs/openai), which Google lists as beta. Create a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey). Which models you can call depends on your account.
- **OpenAI** reasoning models need `OPENAI_REASONING_EFFORT` at its default of `none` for tool use.
- **Unsloth** is not a chat server. Serve a model with an OpenAI-compatible server, then connect Relay to it. For tool calling, use vLLM or SGLang, or llama-server with `--jinja`.

  ```bash
  # vLLM (default port 8000)
  vllm serve unsloth/Llama-3.2-1B-Instruct
  python unsloth_chat.py

  # llama-server (port 8001)
  llama-server --model your-unsloth.gguf --port 8001 --jinja
  set UNSLOTH_BASE_URL=http://127.0.0.1:8001/v1
  python unsloth_chat.py
  ```

  `python unsloth_chat.py` is the same as `python relay.py` with `LLM_PROVIDER=unsloth`.

## Configuration

Settings are environment variables. Relay reads them from `.env` in the project folder or from your shell. The defaults work for LM Studio on the same machine, so you only need to set what you change.

**General**

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `lm_studio` | `lm_studio`, `openai`, `anthropic`, `google` or `unsloth` |
| `RELAY_HOST` | `127.0.0.1` | Web UI bind address. Keep it on localhost |
| `RELAY_PORT` | `7860` | Web UI port |
| `LM_STUDIO_MAX_TOKENS` | `32768` | Max completion tokens per model round, for every provider |
| `LM_STUDIO_TEMPERATURE` | `0.3` | Sampling temperature, for every provider that accepts one |
| `LM_STUDIO_SKILLS_DIRS` | — | Extra skill directories, separated by `;` on Windows and `:` on Unix |
| `LM_STUDIO_INSPECT_PAGE_HEADED` | — | Set to `1` to show the browser window used by `inspect_page` |
| `LM_STUDIO_ALLOW_UNRESTRICTED_PATHS` | — | Set to `1` to let file tools and `cd` leave the project folder |

**LM Studio and Unsloth (local)**

| Variable | Default | Description |
|----------|---------|-------------|
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | LM Studio API base URL |
| `LM_STUDIO_API_KEY` | `lm-studio` | Ignored by LM Studio; the SDK requires a value |
| `LM_STUDIO_MODEL` | *(auto-detect)* | Pin a specific model id |
| `UNSLOTH_BASE_URL` | `http://127.0.0.1:8000/v1` | Unsloth OpenAI-compatible endpoint |
| `UNSLOTH_API_KEY` | `sk-no-key-required` | Ignored by most local servers; the SDK requires a value |
| `UNSLOTH_MODEL` | *(auto-detect)* | Pin a specific model id |

**OpenAI**

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | — | Required when `LLM_PROVIDER=openai` |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API base URL |
| `OPENAI_CONTEXT_WINDOW` | `128000` | Input-token budget used to trim history |
| `OPENAI_REASONING_EFFORT` | `none` | Reasoning effort for reasoning models |

**Anthropic**

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required when `LLM_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL` | — | Required when `LLM_PROVIDER=anthropic` |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com/v1` | API base URL |
| `ANTHROPIC_CONTEXT_WINDOW` | `200000` | Input-token budget used to trim history. Raise it for 1M-context models |
| `ANTHROPIC_TEMPERATURE` | *(unset)* | 0 to 1. Leave unset for Claude 4.7 and later |
| `ANTHROPIC_WORKSPACE_ID` | — | Workspace header for some multi-workspace keys |

**Google (Gemini)**

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_AI_STUDIO_API_KEY` | — | Required when `LLM_PROVIDER=google` |
| `GOOGLE_AI_STUDIO_MODEL` | — | Required when `LLM_PROVIDER=google` |
| `GOOGLE_AI_STUDIO_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | API base URL |
| `GOOGLE_AI_STUDIO_CONTEXT_WINDOW` | `1000000` | Input-token budget used to trim history. Lower it to cap cost |
| `GOOGLE_AI_STUDIO_TEMPERATURE` | *(unset)* | 0 to 2. Unset uses the model default |
| `GOOGLE_AI_STUDIO_REASONING_EFFORT` | *(unset)* | `none`, `minimal`, `low`, `medium` or `high` |

Session data is stored in your home folder: logs in `~/.relay_logs/`, chat history in `~/.relay_history.json`, the open project in `~/.relay_project.json`, and attachments in `~/.relay_attachments/`.

## Agent Skills

A skill is a folder containing a `SKILL.md` file. The file starts with YAML frontmatter that has at least `name` and `description`, followed by the instructions for the model:

```
skills/
  example/
    SKILL.md
```

The model can call `list_skills()` and `read_skill(name)` to load a skill when it is relevant. Relay looks in `skills/` in the project, in `~/.relay/skills/`, and in any folders listed in `LM_STUDIO_SKILLS_DIRS`. See [`skills/example/SKILL.md`](skills/example/SKILL.md) for a working example.

## Project layout

```
relay/          Python package: API, chat engine, providers, tools
static/         Web UI (HTML and JavaScript)
skills/         Bundled Agent Skills
tests/          Unit tests
evals/          Evaluation harness for the agent
docs/           Design and refactor notes
relay.py        Entry script
unsloth_chat.py Entry script for the Unsloth provider
```

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
python -m evals selfcheck
```

`pytest` runs the unit tests. `selfcheck` replays scripted agents through the real engine and scorer, so it needs no model and no API key. To measure a real model, see [`evals/README.md`](evals/README.md).

## Upgrading from lm-studio-chat

Relay was previously named lm-studio-chat. To keep an existing setup working:

- Rename the entry script: `python lm_studio_chat.py` becomes `python relay.py`.
- Rename the environment variables `LM_STUDIO_CHAT_HOST` and `LM_STUDIO_CHAT_PORT` to `RELAY_HOST` and `RELAY_PORT`.
- To keep your history, logs and attachments, move `~/.lm_studio_chat_*` to `~/.relay_*`, and move `~/.lm_studio_chat/skills` to `~/.relay/skills`.

## License

[MIT](LICENSE)
