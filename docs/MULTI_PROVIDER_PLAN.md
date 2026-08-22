# Multi-provider LLM plan

Goal: keep LM Studio (local) default; add external OpenAI-compatible providers (OpenAI first).

Constraint: minimal diff. OpenAI SDK already abstracts both — no custom HTTP client.

---

## Current coupling

| Location | LM Studio–specific |
|----------|-------------------|
| `config.py` | `LM_STUDIO_*` env, `LM_STUDIO_BASE_URL` default |
| `state.py` | `create_app_state()` builds single `OpenAI(base_url=LM_STUDIO_*)` |
| `main.py` | `detect_model_id()` at startup; prints LM Studio URL |
| `lm_client.py` | model detect + native `/api/v0` context + GPU/VRAM telemetry |
| `chat/engine.py` | `state.client.chat.completions.create(...)` — provider-agnostic already |
| `api/routes/status.py` | exposes `base_url`; runtime always calls LM telemetry |
| UI `static/` | "model" label only; GPU widget assumes local |

Chat engine + tools need no provider logic if client+model_id are correct.

---

## Design

### Provider config (`config.py`)

```python
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "lm_studio")  # lm_studio | openai
```

Per-provider env (keep `LM_STUDIO_*` for backward compat):

| Provider | base_url | api_key | model |
|----------|----------|---------|-------|
| `lm_studio` | `LM_STUDIO_BASE_URL` (default localhost:1234/v1) | `LM_STUDIO_API_KEY` | auto-detect or `LM_STUDIO_MODEL` |
| `openai` | `OPENAI_BASE_URL` (default `https://api.openai.com/v1`) | `OPENAI_API_KEY` (**required**) | `OPENAI_MODEL` (**required**) |

Shared: `LM_STUDIO_MAX_TOKENS`, `LM_STUDIO_TEMPERATURE` — rename aliases later; don't break env now.

### `LLMProvider` dataclass (`providers/base.py`)

```python
@dataclass(frozen=True)
class LLMProvider:
    id: str                    # "lm_studio" | "openai"
    label: str                 # UI display
    client: OpenAI
    model_id: str
    base_url: str
    stream_usage: bool         # False for providers that reject stream_options
    local: bool                # True → show GPU telemetry
```

Factory: `providers/factory.py::create_provider() -> LLMProvider`
- Validates env per provider; raises clear `RuntimeError` on missing key/model.
- `lm_studio`: move `detect_model_id` here (from `lm_client.py`).
- `openai`: require `OPENAI_MODEL`; optional `client.models.list()` sanity check.

### AppState (`state.py`)

Replace `client: OpenAI` + loose `model_id` with:

```python
provider: LLMProvider
# property shortcuts: state.client, state.model_id → provider.client, provider.model_id
```

`create_app_state(provider: LLMProvider | None = None)` — if None, call factory.

### Telemetry split

- `lm_client.py` → keep LM-only helpers (`fetch_context_capacity`, `fetch_gpu_status`, …).
- `providers/telemetry.py` (or inline in status route):
  - `local` → existing GPU/context endpoints
  - `openai` → return `context_length: null`, `gpu: null` (or static model window if we add a small map later)

### Status API (`api/routes/status.py`)

Extend `/api/status`:

```json
{
  "provider": "lm_studio",
  "provider_label": "LM Studio (local)",
  "model": "...",
  "base_url": "...",
  "local": true
}
```

`/api/status/runtime`: gate LM calls on `state.provider.local`.

### UI (`static/app.js`, `index.html`)

- Show provider label near model name (one line).
- Hide or dim GPU widget when `local: false` (check `/api/status` on load).
- No in-app provider switch in v1 — env-only at startup.

### Security / UX

- Startup banner: warn when `provider.id != "lm_studio"` (data leaves machine).
- `.env.example`: add `LLM_PROVIDER`, `OPENAI_*`.
- README: short provider section (after impl).

### Out of scope v1

- Per-session provider override
- Anthropic native API (different SDK); could add later as another OpenAI-compatible proxy
- Provider picker in UI without restart
- Renaming package away from `lm_studio_chat`

---

## File map

```
lm_studio_chat/providers/
  __init__.py
  base.py          # LLMProvider
  factory.py       # create_provider()
  lm_studio.py     # detect_model_id (moved from lm_client)
  openai.py        # validate + resolve model
```

Touch: `config.py`, `state.py`, `main.py`, `api/routes/status.py`, `api/routes/chat.py` (use state.provider), `chat/engine.py` (stream_usage flag), `.env.example`, `README.md`, root shim docstring.

Keep: `lm_client.py` for LM telemetry only (import from providers/lm_studio for detect if needed).

---

## Phases (app must run after each)

### P1 — Provider module + config
- [x] Add `providers/*`, env vars, factory

### P2 — Wire AppState + main
- [x] `create_app_state()` uses factory
- [x] `main.py` prints provider + model
- [x] Default `LLM_PROVIDER=lm_studio` → zero behavior change

### P3 — Engine + status
- [x] `run_chat`: pass `stream_usage` from provider; keep try/except fallback
- [x] Status routes provider-aware; runtime gated

### P4 — UI + docs
- [x] Provider label; hide GPU when external
- [x] `.env.example`, README, shim docstring

### P5 — Smoke
- [x] `LLM_PROVIDER=lm_studio` — existing flow
- [x] `LLM_PROVIDER=openai` + key + model — factory + status API verified

---

## Risks

| Risk | Mitigation |
|------|------------|
| OpenAI tool schema differences | Same schemas; test one tool round |
| `stream_options` unsupported | `provider.stream_usage`; existing fallback in engine |
| Vision models differ | No change; attachments already OpenAI-format |
| External + shell tools | Document risk; no code block v1 |
| Env rename churn | Keep all `LM_STUDIO_*` names |

---

## Success

- Default startup unchanged (LM Studio).
- `LLM_PROVIDER=openai` + key + model → streaming chat + tool loop works.
- Status UI reflects provider; GPU hidden for external.
