# relay.py refactor plan

Monolith: **~4024 → ~35 lines** (Phase 8 complete). Split by **domain**, not line count. **Replace module globals first** — file splits alone cause circular imports.

Entry points (all equivalent):
- `python relay.py` → uvicorn on `:7860`
- `python -m relay` → same

---

## Progress (Phases 0–8 done)

### Package: `relay/`

| Module | Status | Notes |
|--------|--------|-------|
| `config.py` | ✅ | env, paths, constants, SYSTEM_PROMPT, attachment allowlists |
| `types.py` | ✅ | ToolResult, ChatPartial, SkillEntry |
| `models.py` | ✅ | ChatRequest, ChatAttachment, StopRequest, … |
| `sse.py` | ✅ | SSE formatting |
| `state.py` | ✅ | AppState, ToolContext, create_app_state() |
| `main.py` | ✅ | bootstrap: detect model, load project, run uvicorn |
| `__main__.py` | ✅ | `python -m relay` |
| `tools/builtin.py` | ✅ | get_current_time, calculate |
| `tools/filesystem.py` | ✅ | read/search/list/write/str_replace + resolve_tool_path |
| `tools/shell.py` | ✅ | run_command, kill_active_command |
| `tools/web.py` | ✅ | web_search, fetch_url (lazy ddgs import) |
| `tools/inspect_page.py` | ✅ | Playwright aria snapshot (lazy playwright import) |
| `tools/schemas.py` | ✅ | TOOL_SCHEMAS (14 tools) |
| `tools/registry.py` | ✅ | TOOL_IMPLS, dispatch_tool, UI helpers, tool_catalog |
| `skills/discovery.py` | ✅ | discover/list/read skills, skill_api_prefix, skills_catalog |
| `sessions/store.py` | ✅ | load/save/find, CRUD (new_session, session_title, …) |
| `sessions/attachments.py` | ✅ | validate, persist, compose, view_attachment, delete on session |
| `project/root.py` | ✅ | open/close/browse, cwd sync, folder picker |
| `project/explorer.py` | ✅ | entries, attachable file kinds |
| `lm_client.py` | ✅ | detect model, context capacity, GPU/VRAM telemetry |
| `logging.py` | ✅ | session logs, reveal-in-finder |
| `chat/prompts.py` | ✅ | build_system_prompt |
| `chat/engine.py` | ✅ | run_chat (streaming + multi-round tools; inner closures kept together) |
| `chat/turns.py` | ✅ | run_user_turn, history/attachment wiring |
| `api/app.py` | ✅ | create_app(state), static mount, index route |
| `api/routes/status.py` | ✅ | /api/status, /api/skills, /api/status/runtime, /api/local-file |
| `api/routes/project.py` | ✅ | /api/project/* |
| `api/routes/sessions.py` | ✅ | /api/sessions/*, /api/stop, /api/open-log |
| `api/routes/chat.py` | ✅ | /api/chat (SSE) |

### Root shim (`relay.py`)

- Docstring (usage / env vars) — preserved for backward compatibility
- Re-exports `main` from `relay.main`

### Key design changes landed

- **No module-level mutable app state** — AppState passed through main → create_app → chat/tools/routes
- **ToolContext** for dispatch (state + optional session_id); view_attachment uses ctx
- **Registry pattern** — tools registered in `tools/registry.py`
- **Chat engine isolated** — `run_user_turn` → `run_chat` in `chat/*`
- **API routers** — domain routers receive `state` via factory; `create_app` wires them together
- **Package entry** — `main()` lives in `relay/main.py`; root file is a thin shim

---

## Target layout (final)

```
relay/
  __init__.py                  ✅  exports create_app, main
  __main__.py                  ✅
  main.py                      ✅
  config.py                    ✅
  models.py                    ✅
  types.py                     ✅
  state.py                     ✅
  sse.py                       ✅
  lm_client.py                 ✅
  logging.py                   ✅
  sessions/
    store.py                   ✅
    attachments.py             ✅
  project/
    root.py                    ✅
    explorer.py                ✅
  skills/
    discovery.py               ✅
  tools/
    registry.py                ✅
    schemas.py                 ✅
    filesystem.py              ✅
    shell.py                   ✅
    web.py                     ✅
    inspect_page.py            ✅
    builtin.py                 ✅
  chat/
    engine.py                  ✅
    turns.py                   ✅
    prompts.py                 ✅
  api/
    app.py                     ✅
    routes/
      status.py                ✅
      project.py               ✅
      sessions.py              ✅
      chat.py                  ✅
static/, skills/               # unchanged
relay.py              ✅  ~35-line backward-compat shim
```

## AppState (central design move) — ✅ implemented

Replace globals: `_SHELL_CWD`, `_PROJECT_ROOT`, `_model_id`, `_request_cancel`, `_session_usage`, `client`, `_sessions_lock`.

```python
@dataclass
class AppState:
    shell_cwd: Path
    project_root: Path | None
    model_id: str | None
    cancel: threading.Event
    session_usage: dict[str, dict[str, Any]]
    client: OpenAI
    sessions_lock: threading.Lock
```

- Pass `state` (or narrow `ToolContext`) into tools, chat engine, routes.
- FastAPI: `app.state.app_state` + closure over `state` in router factories.

## Tool registry — ✅ implemented

`registry.py` collects TOOL_IMPLS + TOOL_SCHEMAS. State-aware tools receive `ctx.state`; view_attachment receives full `ToolContext`.

## Do NOT

- Split `_run_chat` inner closures across many files yet.
- Big-bang rename; one domain per PR.
- Heavy DI framework — dataclass + `app.state` is enough.

---

## Phases (incremental; app must run after each)

### Phase 0 — Baseline
- [x] Entry: `python relay.py` → uvicorn on `:7860`
- [x] Smoke test verified by user (Phases 1–2)

### Phase 1 — Leaf extractions (no globals) ✅
- [x] `config.py` — paths, env, constants, attachment allowlists, SYSTEM_PROMPT
- [x] `types.py` — ToolResult, ChatPartial, SkillEntry
- [x] `models.py` — ChatRequest, ChatAttachment, etc.
- [x] `sse.py` — `_sse()`
- [x] Monolith imports from new modules; behavior unchanged

### Phase 2 — AppState ✅
- [x] `state.py` — AppState dataclass + factory from env
- [x] `main()` builds state; pass to `create_app(state)`
- [x] Thread state through chat + all routes; globals deleted
- [x] Tools receive `ToolContext(state, session_id?)` instead of reading `_SHELL_CWD` etc.

### Phase 3 — Tools ✅
- [x] `tools/registry.py` — dispatch, collect registrations
- [x] Extract: `filesystem.py`, `shell.py`, `builtin.py`
- [x] Extract: `web.py`, `inspect_page.py` (lazy/optional imports for ddgs/playwright)
- [x] Extract skill tools → `skills/discovery.py`
- [x] `view_attachment` → `sessions/attachments.py`, register in registry
- [x] `tools/schemas.py` — TOOL_SCHEMAS separated from registry

### Phase 4 — Sessions & project ✅
- [x] Finish `sessions/store.py` — session CRUD (_new_session, _sessions_summary, …)
- [x] Finish `sessions/attachments.py` — validate, persist, compose messages
- [x] `project/root.py` — open/close/browse, cwd sync
- [x] `project/explorer.py` — entries, attachable file kinds

### Phase 5 — LM client & logging ✅
- [x] `skills/discovery.py` — done in Phase 3
- [x] `lm_client.py` — detect model, context capacity, GPU/VRAM
- [x] `logging.py` — session logs, reveal-in-finder

### Phase 6 — Chat engine ✅
- [x] `chat/prompts.py` — `build_system_prompt`
- [x] `chat/engine.py` — `run_chat` (single file; inner closures kept together)
- [x] `chat/turns.py` — `run_user_turn`, history/attachment wiring

### Phase 7 — API layer ✅
- [x] `api/app.py` — `create_app(state)`
- [x] Routers: `status`, `project`, `sessions`, `chat` (SSE)
- [x] Handlers stay thin; logic lives in chat/sessions/project modules
- [x] `skills_catalog` → `skills/discovery.py`

### Phase 8 — Entry shim & cleanup ✅
- [x] `relay/main.py` — bootstrap `main()` in package
- [x] `relay/__main__.py` — `python -m relay`
- [x] Root `relay.py` — thin re-export (docstring preserved)
- [x] API smoke test pass (TestClient: `/`, `/api/status`, `/api/sessions`, …)

---

## Success criteria

- [x] `python relay.py` works unchanged for users
- [x] `python -m relay` works
- [x] No module-level mutable app state
- [x] Tools testable without FastAPI or LM Studio (tools/* + registry)
- [x] Optional deps (playwright, ddgs) isolated so import failures are localized
- [x] Chat engine testable without FastAPI (chat/* + registry mocks)
- [x] API layer split by domain (api/routes/*)
- [x] Monolith fully replaced by package entry (root file is backward-compat shim only)
