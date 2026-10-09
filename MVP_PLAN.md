# MVP plan

Goal: make this repo something a stranger can clone, run, and **trust on a real coding task** — not add product surface.

Core loop already works (streaming chat, tools, sessions, project explorer, LM Studio + OpenAI). Remaining work is reliability, truthful docs/UI, and “I can see what the agent just did.”

Constraint: app must still run after each phase. Default `LLM_PROVIDER=lm_studio` behavior stays the default. No auth, no installer, no in-UI provider picker, no full editor-with-save.

Follow this file in order. Check boxes as phases land. Do not start a later phase until the earlier one’s success checks pass.

---

## Out of scope (do not do these in this plan)

- Editable editor + save, inline diffs, undo
- Per-session provider override / Anthropic / UI provider switcher
- Auth, packaging (`pyproject.toml`, pipx, installer)
- CDN-free UI (document network need only if you touch README)
- GPU meter polish, Test-vs-All explorer, KaTeX, minimap
- Renaming the package off `lm_studio_chat`
- Broad test suite (smoke only, in P7)

---

## Current bugs / lies this plan exists to fix

| # | Status | Problem | Why it blocks MVP |
|---|--------|---------|-------------------|
| 1 | [x] Fixed | Explorer refreshes only on successful `write_file`; editor tabs never reload | Model is told to prefer `str_replace`. After an edit the UI still shows the old file. |
| 2 | [x] Fixed | Full chat history is sent every turn; no truncation | Long sessions overflow the context window and look like a random API error. |
| 3 | [x] Fixed | `_inspect_page_headless()` always returns `False`; env var is commented out | README documents `LM_STUDIO_INSPECT_PAGE_HEADED`; code ignores it. Tool schema says “headless.” |
| 4 | [x] Fixed | File tools accept any absolute path | Explorer is sandboxed; `read_file` / `write_file` / `str_replace` / `run_command` are not. |
| 5 | [x] Fixed | System prompt claims vision unconditionally | Many LM Studio models cannot see images. |
| 6 | [x] Fixed | Optional tools always appear available | Missing `ddgs` / `playwright` only fails mid-chat. |
| 7 | [x] Fixed | README clone URL is `YOUR_USERNAME`; startup error is a traceback | First-run friction for anyone who is not you. |

---

## File map (where work will land)

```
static/app.js                      P1 explorer + editor reload; bump ?v= in index.html
static/index.html                  P1 cache-bust; P5/P6 UI copy if needed
lm_studio_chat/tools/filesystem.py P4 path sandbox
lm_studio_chat/tools/shell.py      P4 cwd / cd sandbox (project root)
lm_studio_chat/tools/inspect_page.py  P3 headless
lm_studio_chat/tools/web.py        P6 availability probe
lm_studio_chat/tools/registry.py   P6 catalog availability
lm_studio_chat/tools/schemas.py    P3 wording if it still says “headless” as a guarantee
lm_studio_chat/chat/turns.py       P2 history window
lm_studio_chat/chat/prompts.py     P5 vision-conditional prompt
lm_studio_chat/config.py           P4/P5 constants + SYSTEM_PROMPT vision block
lm_studio_chat/providers/*         P5 vision capability flag if cheap
lm_studio_chat/api/routes/status.py  P6 tools/skills availability; P7 health
lm_studio_chat/api/routes/chat.py  P2 overflow error surfacing
lm_studio_chat/main.py             P7 startup message
README.md                          P3/P5/P7 docs truth
.env.example                       P3 headed env (already present — verify)
```

Keep `run_chat` inner closures in `chat/engine.py`. Do not reintroduce module-level mutable app state.

---

## P1 — See the agent’s edits  ← do this first

**Why first:** if the user cannot see file changes, nothing else in the product matters.

### Behavior

On SSE `done` (and `error` if tools already ran):

1. Refresh the explorer when any **successful** mutating file tool ran:
   - `write_file`
   - `str_replace`
   - optionally `run_command` with `ok !== false` (refresh only; do not try to guess which files changed)
2. Reload **open editor tabs** whose paths may have changed:
   - Parse `path` from tool event `arguments` (already on the event).
   - Match against `state.editorTabs` (normalize `\` → `/`).
   - Re-fetch content via existing `fetchProjectFile` and replace tab text (keep tab open, keep active tab).
   - If the file vanished, show the existing editor error state for that tab.
3. Clicking an **already-open** tab must not skip reload forever. Today `openEditorFile` returns early on `existing`. Either:
   - add `openEditorFile(rel, { reload: true })` used after tool turns, **or**
   - change the existing-tab path to activate without treating that as “content is fresh.”

### Files

- `static/app.js`
  - `shouldRefreshExplorerForToolEvents` (~line 635) — include `str_replace` (and `run_command` if you take the optional branch)
  - `handleSse` (~line 3835) — also refresh/reload on `error` when `tool_events` exist
  - `openEditorFile` (~line 2105) — reload path
  - new helper e.g. `reloadEditorTabsForToolEvents(toolEvents)`
- `static/index.html` — bump `app.js?v=46` → `v=47` (or next integer)

### Do not

- Build a file watcher / polling loop
- Implement editor save
- Refresh on `read_file` / `search_file` / `list_dir`

### Success

- Open a project file in the editor, ask the model to `str_replace` it, and the open tab plus explorer update when the turn finishes.
- `write_file` of a **new** file appears in the explorer without a manual refresh.

---

## P2 — Context overflow without a mysterious crash

**Why:** long chats are the first “it broke” report after the novelty wears off.

### Behavior

1. Before `run_chat`, estimate prompt size (chars/4 is fine; no tokenizer required).
2. Budget against the loaded context window when known (`lm_client.effective_context_window` / last runtime caps), else a conservative fallback (e.g. `min(MAX_TOKENS * 4, 32_000)` tokens of **input** headroom is wrong — use window minus `MAX_TOKENS` minus a reserve for tools).
3. Drop **oldest user+assistant pairs** from the replayed history until the budget fits. Never drop:
   - the system prompt
   - the current user turn
   - the most recent N pairs (N=1 is the minimum; N=2 is better)
4. If even that cannot fit (giant current message / image), fail the turn with a clear SSE `error` message: “This message is too large for the model context window.” Do not send a request you know will 400.
5. Optional but useful: prepend a one-line system or user note when history was trimmed: `[Older messages omitted to fit the context window.]`
6. UI: if `/api/status/runtime` reports a window and last usage is ≥ ~85%, the existing ring already goes rose — keep it. Do not add a new widget. If the turn errors with overflow, `handleSse` already shows `payload.message` in `log-status`.

### Files

- `lm_studio_chat/chat/turns.py` — trim in `run_user_turn` before calling `run_chat`
- `lm_studio_chat/lm_client.py` — reuse `effective_context_window`; may cache last caps on `AppState` if you already fetch them on status (do not call nvidia-smi from the chat path)
- `lm_studio_chat/state.py` — optional `context_window: int | None` filled by status/runtime or a cheap caps fetch at turn start for local providers
- `lm_studio_chat/api/routes/chat.py` — only if you need to pass window in; prefer keeping logic in `turns.py`

### Do not

- Summarize history with a second model call
- Truncate mid-message with `...` in a way that looks like the user said it
- Change `MAX_TOKENS` defaults

### Success

- A long session continues instead of dying at the API. Older turns disappear from the **model** context only (UI history stays complete).
- An oversized single message yields a readable error, not a stack trace in the assistant bubble.

---

## P3 — `inspect_page` headless matches docs

### Behavior

Restore `_inspect_page_headless()`:

```python
def _inspect_page_headless() -> bool:
    headed = os.getenv("LM_STUDIO_INSPECT_PAGE_HEADED", "").strip().lower()
    return headed not in ("1", "true", "yes")
```

Default = headless. `LM_STUDIO_INSPECT_PAGE_HEADED=1` shows the window.

Update tool schema description if it claims headless as the only mode. Keep README / `.env.example` in sync (they already describe this — verify, don’t invent a second env name).

### Files

- `lm_studio_chat/tools/inspect_page.py`
- `lm_studio_chat/tools/schemas.py` (wording only)
- `README.md` / `.env.example` (confirm; edit only if stale)

### Success

- Default run: no Chromium window.
- Env set: window appears.
- README matches the function.

---

## P4 — Sandbox file tools to the project (default)

**Why:** explorer already refuses paths outside the project; tools do not. MVP default should match user expectation: “this is my project agent.”

### Behavior

1. Add `resolve_tool_path` confinement:
   - If `state.project_root` is set, resolved path must be `project_root` or a child. Otherwise return `Error: path is outside the open project: ...`
   - If no project is open, keep today’s behavior (resolve against `shell_cwd`) **or** confine to `shell_cwd` the same way. Prefer confine-to-cwd when no project is open so `cd` + relative paths still work, but `C:\Windows\...` is rejected unless opted in.
2. Opt-out (explicit, documented): e.g. `LM_STUDIO_ALLOW_UNRESTRICTED_PATHS=1` restores current “any path the process can see” behavior. Default **unset** = restricted.
3. `run_command`:
   - Bare `cd` may not leave the sandbox root.
   - Do **not** try to parse every command for path escapes (impossible with `shell=True`). Document that unrestricted shell is still the dangerous part; file tools are the ones we actually lock.
   - Optional stretch (only if cheap): if project is open, reject `cd` targets outside it. Leave command execution otherwise unchanged.
4. System prompt: one line that relative paths resolve under the open project and paths outside it are rejected.

### Files

- `lm_studio_chat/tools/filesystem.py` — `resolve_tool_path`
- `lm_studio_chat/tools/shell.py` — `resolve_cd_target` / `cd` handling
- `lm_studio_chat/config.py` — env flag + prompt sentence
- `README.md` Security section — say file tools are project-scoped; shell is not fully scoped; opt-out env

### Do not

- Implement a real OS sandbox / container
- Break absolute paths that are **inside** the project
- Change explorer `resolve_project_child` (already correct)

### Success

- With a project open, `read_file` of `C:\` (or `/etc/passwd`) returns an Error string, not contents.
- Relative edits inside the project still work.
- Unrestricted env restores old behavior.

---

## P5 — Don’t promise vision the model doesn’t have

### Behavior

1. Treat vision as **unknown / false** unless we know otherwise.
   - OpenAI: models with `gpt-4o`, `gpt-4.1`, `o4`, or `vision` in the id (keep a small allow-prefix list; don’t scrape the network).
   - LM Studio: if native `/api/v0` or `/api/v1` model metadata exposes vision/multimodal, use it. If not, **do not claim vision**.
2. `SYSTEM_PROMPT` vision block is appended only when `provider.supports_vision` (add field on `LLMProvider`, default `False`).
3. If the user attaches an image and vision is unsupported:
   - Still persist the attachment for the UI.
   - API content should be text: `[Attached image: name (id: …). This model cannot view images; describe it in text or switch to a vision model.]`
   - Do not send `image_url` parts that the backend will reject or ignore.
4. README feature bullet: “Image attachments (when the loaded model supports vision).”

### Files

- `lm_studio_chat/providers/base.py` — `supports_vision: bool = False`
- `lm_studio_chat/providers/lm_studio.py` / `openai_provider.py`
- `lm_studio_chat/chat/prompts.py`
- `lm_studio_chat/config.py` — split vision instructions out of the always-on prompt
- `lm_studio_chat/sessions/attachments.py` — `compose_user_message` / reinjection gated on vision
- `lm_studio_chat/api/routes/status.py` — expose `supports_vision` so the UI can hint
- `static/app.js` — optional one-line composer hint when attaching an image and `supports_vision` is false
- `README.md`

### Success

- Text-only local model: no “you can see images” in the system prompt; image attach still works in the UI; model is told it cannot view them.
- A known vision model (e.g. `gpt-4o`) still gets `image_url` parts.

---

## P6 — Optional tools advertise availability

### Behavior

Extend `/api/status` tool catalog entries:

```json
{ "name": "web_search", "description": "...", "available": true, "unavailable_reason": null }
```

- `web_search` / `fetch_url`: `available=false` if `ddgs` (or fallback) / fetch stack missing. `fetch_url` can stay available with stdlib-only if you keep the regex fallback; still mark `web_search` false without `ddgs`.
- `inspect_page`: false if `playwright` import fails. Do not run `playwright install` from status. Optional second check: Chromium executable missing → unavailable with the install hint already used in the tool.
- Sidebar: unavailable tools stay listed but visually muted, with the reason (one short line).
- `tool_catalog()` in `registry.py` is the single source; status route should not duplicate probe logic.

### Files

- `lm_studio_chat/tools/web.py` — `web_search_available()` helper
- `lm_studio_chat/tools/inspect_page.py` — `inspect_page_available()` helper
- `lm_studio_chat/tools/registry.py` — catalog includes availability
- `lm_studio_chat/api/routes/status.py`
- `static/app.js` — `applyBasicStatus` tool chips
- bump `app.js?v=` again if P1 already shipped a bump and this is a later change

### Do not

- Hide tools from the model schema when unavailable (the model should get the same error string it gets today if it still calls them). **Or** omit unavailable tools from `TOOL_SCHEMAS` at request time — omitting is cleaner. Prefer **omit from `TOOL_SCHEMAS` when unavailable** so the model doesn’t waste a round. Keep them in the UI catalog as disabled.
- Install packages from the status endpoint.

### Success

- Fresh venv without extra requirements: sidebar shows web/browser tools as unavailable with install hints; chat still works; model is not offered `web_search` / `inspect_page`.
- After `pip install -r requirements-web.txt`, `web_search` becomes available on the next `/api/status` (restart is OK for MVP; live re-probe on status is better and cheap).

---

## P7 — First-run honesty (docs + startup)

Do this last so README describes the product that actually exists.

### README

- Replace `github.com/YOUR_USERNAME/lm-studio-chat.git` with the real remote if this repo has one; otherwise use a local-only snippet (`cd` into the folder you already have) and drop the fake clone URL.
- Vision bullet matches P5.
- Security: file tools project-scoped; shell still powerful; `LM_STUDIO_ALLOW_UNRESTRICTED_PATHS`.
- Optional deps: note that the UI lists them as unavailable until installed.
- Confirm `LM_STUDIO_INSPECT_PAGE_HEADED` after P3.

### Startup (`main.py` + provider)

`create_lm_studio_provider` already raises a clear `RuntimeError` if LM Studio is down or no model is loaded. Keep that. Make `main()` print it without a huge traceback if possible (`try/except RuntimeError` around `create_app_state()`, print the message, `sys.exit(1)`).

Do not auto-open the browser if bootstrap failed.

### Success

- README can be followed without placeholders or lying about vision/headless/sandbox.
- Stopping LM Studio and running the app prints the existing connection/model message and exits 1.

---

## Optional P8 — Tiny smoke (only if P1–P7 are done and cheap)

No pytest garden. One module or `python -c` is enough:

- `TestClient`: `GET /`, `GET /api/status` (may need a fake provider injected into `create_app_state`)
- `resolve_tool_path` rejects outside-project paths
- `_inspect_page_headless` respects env

Skip if injecting a fake `LLMProvider` fights the factory. Do not mock LM Studio just to have a test.

---

## Suggested order and effort

| Phase | Status | Focus | Effort |
|-------|--------|-------|--------|
| P1 | [x] Completed | Explorer + editor reload | S |
| P2 | [x] Completed | History window | M |
| P3 | [x] Completed | inspect_page headless | S |
| P4 | [x] Completed | Path sandbox | M |
| P5 | [x] Completed | Vision honesty | M |
| P6 | [x] Completed | Tool availability | S–M |
| P7 | [x] Completed | README + startup | S |
| P8 | [x] Completed | Smoke | S, optional |

P3 can be done in the same sitting as P1 if you want a quick win; do not skip P1.

---

## Done when (MVP gate)

A person who is not the author can:

- [x] 1. Start the app with LM Studio running (or get a one-line error if it isn’t).
- [x] 2. Open this repo as the project.
- [x] 3. Ask the model to change an existing file via `str_replace` and **see the new contents in the open editor** without a manual refresh.
- [x] 4. Keep chatting in a long session without a raw context-overflow stack trace.
- [x] 5. Fail to read a file outside the project (default).
- [x] 6. Attach an image to a text-only model without the prompt claiming the model can see it.
- [x] 7. See in the sidebar that web/browser tools are missing until optional extras are installed.
- [x] 8. Trust the README on clone, vision, headless inspect, and security.

When all eight are true, mark this plan complete. Then stop — diffs, save-in-editor, and history summarization are post-MVP. [x] Plan complete.
