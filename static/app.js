(() => {
  "use strict";

  const IMAGE_EXTS = new Set([
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".avif",
  ]);
  const FILE_EXTS = new Set([
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".tsv",
    ".json",
    ".jsonc",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".py",
    ".pyi",
    ".rb",
    ".php",
    ".java",
    ".kt",
    ".kts",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".cxx",
    ".hpp",
    ".hxx",
    ".cs",
    ".swift",
    ".m",
    ".mm",
    ".scala",
    ".lua",
    ".r",
    ".pl",
    ".pm",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".sql",
    ".vue",
    ".svelte",
    ".dart",
    ".zig",
    ".nim",
    ".proto",
    ".graphql",
    ".gql",
    ".tf",
    ".hcl",
    ".cmake",
    ".mk",
    ".makefile",
    ".dockerfile",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".gitignore",
    ".editorconfig",
    ".properties",
  ]);
  const MAX_TEXT_BYTES = 512 * 1024;
  const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
  const MAX_ATTACHMENTS = 8;
  const EXPLORER_PATH_MIME = "application/x-explorer-path";
  const EXPLORER_VIEW_STORAGE_KEY = "explorer-view-mode";
  const EXPLORER_TEST_MODE_DIRS = new Set(["tests", "pages", "helpers"]);

  const PANEL_LAYOUT = {
    explorer: { min: 168, max: 520, default: 256, storageKey: "panel-explorer-width" },
    chat: { min: 260, max: 720, default: 360, storageKey: "panel-chat-width" },
    editorMin: 300,
  };

  function readStoredPanelWidth(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      const value = raw ? Number.parseInt(raw, 10) : NaN;
      return Number.isFinite(value) ? value : fallback;
    } catch {
      return fallback;
    }
  }

  function storePanelWidth(key, width) {
    try {
      localStorage.setItem(key, String(Math.round(width)));
    } catch {
      /* ignore quota / private mode */
    }
  }

  function clampExplorerWidth(width) {
    const max = Math.min(PANEL_LAYOUT.explorer.max, Math.round(window.innerWidth * 0.42));
    return Math.max(PANEL_LAYOUT.explorer.min, Math.min(width, max));
  }

  function clampChatWidth(width) {
    const workspaceW = els.workspacePanel
      ? els.workspacePanel.getBoundingClientRect().width
      : window.innerWidth;
    const maxByWorkspace = workspaceW - PANEL_LAYOUT.editorMin - 12;
    const max = Math.min(
      PANEL_LAYOUT.chat.max,
      Math.round(window.innerWidth * 0.38),
      maxByWorkspace
    );
    return Math.max(PANEL_LAYOUT.chat.min, Math.min(width, max));
  }

  function applyExplorerWidth(width, { persist = false } = {}) {
    if (!els.explorerPanel) return;
    const next = clampExplorerWidth(width);
    els.explorerPanel.style.width = `${next}px`;
    if (persist) storePanelWidth(PANEL_LAYOUT.explorer.storageKey, next);
    return next;
  }

  function applyChatWidth(width, { persist = false } = {}) {
    if (!els.chatPanel) return;
    const next = clampChatWidth(width);
    els.chatPanel.style.width = `${next}px`;
    if (persist) storePanelWidth(PANEL_LAYOUT.chat.storageKey, next);
    return next;
  }

  function syncPanelWidths({ persist = false } = {}) {
    const explorer = readStoredPanelWidth(
      PANEL_LAYOUT.explorer.storageKey,
      PANEL_LAYOUT.explorer.default
    );
    const chat = readStoredPanelWidth(PANEL_LAYOUT.chat.storageKey, PANEL_LAYOUT.chat.default);
    applyExplorerWidth(explorer, { persist });
    applyChatWidth(chat, { persist });
  }

  function bindPanelResize(handle, { getWidth, setWidth, direction = 1 }) {
    if (!handle) return;

    let startX = 0;
    let startWidth = 0;
    let dragging = false;

    const finish = () => {
      if (!dragging) return;
      dragging = false;
      handle.classList.remove("is-dragging");
      document.body.classList.remove("panel-resizing");
      try {
        handle.releasePointerCapture?.(handle._panelPointerId);
      } catch {
        /* ignore */
      }
      delete handle._panelPointerId;
    };

    handle.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      dragging = true;
      startX = e.clientX;
      startWidth = getWidth();
      handle.classList.add("is-dragging");
      document.body.classList.add("panel-resizing");
      handle._panelPointerId = e.pointerId;
      handle.setPointerCapture(e.pointerId);
    });

    handle.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const delta = e.clientX - startX;
      setWidth(startWidth + direction * delta, { persist: false });
    });

    handle.addEventListener("pointerup", (e) => {
      if (!dragging) return;
      setWidth(getWidth(), { persist: true });
      finish();
    });
    handle.addEventListener("pointercancel", finish);

    handle.addEventListener("dblclick", () => {
      const defaults =
        handle.id === "resize-explorer"
          ? PANEL_LAYOUT.explorer.default
          : PANEL_LAYOUT.chat.default;
      setWidth(defaults, { persist: true });
    });
  }

  function initPanelResizers() {
    syncPanelWidths();

    bindPanelResize(els.resizeExplorer, {
      direction: 1,
      getWidth: () => els.explorerPanel?.getBoundingClientRect().width || PANEL_LAYOUT.explorer.default,
      setWidth: (width, opts) => applyExplorerWidth(width, opts),
    });

    bindPanelResize(els.resizeChat, {
      direction: -1,
      getWidth: () => els.chatPanel?.getBoundingClientRect().width || PANEL_LAYOUT.chat.default,
      setWidth: (width, opts) => applyChatWidth(width, opts),
    });

    window.addEventListener("resize", () => {
      syncPanelWidths();
    });
  }

  const MIME_TO_IMAGE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/avif": ".avif",
  };

  const state = {
    sessions: [],
    currentId: null,
    messages: [],
    busy: false,
    pendingDeleteId: null,
    attachments: [],
    selectedSkill: null,
    skills: [],
    skillsMenuOpen: false,
    // Context meter: `used` is the last turn's total tokens; `window` is the
    // loaded context length; `max` is the model's architectural ceiling.
    ctx: { used: null, window: null, max: null },
    gpuLoaded: false,
    localProvider: true,
    supportsVision: false,
    toolsExpanded: false,
    chatsExpanded: false,
    autoScrollMessages: true,
    project: null,
    explorerExpanded: new Set(),
    explorerEntries: new Map(),
    explorerSelected: null,
    explorerViewMode: readExplorerViewMode(),
    explorerLoading: false,
    explorerDragPath: null,
    editorPath: null,
    editorText: "",
    editorTabs: [],
    editorActivePath: null,
    minimapDragging: false,
    requestStartedAt: null,
    chatAbortController: null,
  };

  let activityTimer = null;

  function activityElapsedMs(item) {
    if (
      item?.active &&
      state.busy &&
      Number.isFinite(state.requestStartedAt)
    ) {
      return Math.max(
        Number.isFinite(item.elapsed_ms) ? item.elapsed_ms : 0,
        Math.round(performance.now() - state.requestStartedAt)
      );
    }
    return Number.isFinite(item?.elapsed_ms) ? item.elapsed_ms : null;
  }

  function refreshLiveActivityElapsed() {
    if (!state.busy || !Number.isFinite(state.requestStartedAt)) return;
    const lastIdx = state.messages.length - 1;
    const last = state.messages[lastIdx];
    if (!last || last.role !== "assistant") return;
    const wrap = els.messageList.children[lastIdx];
    if (!wrap) return;
    const body = wrap.querySelector("[data-msg-body]");
    if (!body) return;

    const segments = last.segments || [];
    for (const seg of segments) {
      if (seg.type !== "status" || !seg.active) continue;
      const row = body.querySelector(`[data-segment-id="${CSS.escape(seg.id || "")}"]`);
      if (!row) continue;
      const elapsedEl = row.querySelector(":scope > .activity-elapsed");
      if (!elapsedEl) continue;
      const ms = activityElapsedMs(seg);
      if (Number.isFinite(ms) && ms >= 0) {
        elapsedEl.dataset.elapsedMs = String(ms);
        elapsedEl.textContent = formatElapsed(ms);
      }
    }

    for (const seg of segments) {
      if (seg.type !== "text" || !seg.active) continue;
      const row = body.querySelector(`[data-segment-id="${CSS.escape(seg.id || "")}"]`);
      if (!row) continue;
      const elapsedEl = row.querySelector(".activity-elapsed");
      if (!elapsedEl) continue;
      const ms = activityElapsedMs(seg);
      if (Number.isFinite(ms) && ms >= 0) {
        elapsedEl.dataset.elapsedMs = String(ms);
        elapsedEl.textContent = formatElapsed(ms);
      }
    }
  }

  function startActivityTimer() {
    if (activityTimer) return;
    activityTimer = window.setInterval(refreshLiveActivityElapsed, 200);
  }

  function stopActivityTimer() {
    if (!activityTimer) return;
    window.clearInterval(activityTimer);
    activityTimer = null;
  }

  const els = {
    sessionList: document.getElementById("session-list"),
    sessionRecent: document.getElementById("session-recent"),
    messageList: document.getElementById("message-list"),
    emptyState: document.getElementById("empty-state"),
    messages: document.getElementById("messages"),
    composer: document.getElementById("composer"),
    composerWrap: document.getElementById("composer-wrap"),
    composerStatus: document.getElementById("composer-status"),
    form: document.getElementById("chat-form"),
    attachChips: document.getElementById("attach-chips"),
    btnAttachImage: document.getElementById("btn-attach-image"),
    btnAttachFile: document.getElementById("btn-attach-file"),
    inputImage: document.getElementById("input-image"),
    inputFile: document.getElementById("input-file"),
    btnSkills: document.getElementById("btn-skills"),
    skillsMenu: document.getElementById("skills-menu"),
    skillsMenuWrap: document.getElementById("skills-menu-wrap"),
    btnSend: document.getElementById("btn-send"),
    btnStop: document.getElementById("btn-stop"),
    btnNew: document.getElementById("btn-new-chat"),
    btnDelete: document.getElementById("btn-delete"),
    btnClearAll: document.getElementById("btn-clear-all"),
    btnOpenLog: document.getElementById("btn-open-log"),
    confirmDelete: document.getElementById("confirm-delete"),
    confirmDeleteText: document.getElementById("confirm-delete-text"),
    btnConfirmDelete: document.getElementById("btn-confirm-delete"),
    btnCancelDelete: document.getElementById("btn-cancel-delete"),
    confirmClear: document.getElementById("confirm-clear"),
    btnConfirmClear: document.getElementById("btn-confirm-clear"),
    btnCancelClear: document.getElementById("btn-cancel-clear"),
    chatTitle: document.getElementById("chat-title"),
    statusPill: document.getElementById("status-pill"),
    statusDot: document.getElementById("status-dot"),
    statusText: document.getElementById("status-text"),
    logStatus: document.getElementById("log-status"),
    statusModel: document.getElementById("status-model"),
    statusProvider: document.getElementById("status-provider"),
    statusCwd: document.getElementById("status-cwd"),
    toolsToggle: document.getElementById("tools-toggle"),
    toolsChevron: document.getElementById("tools-chevron"),
    toolsCount: document.getElementById("tools-count"),
    toolsList: document.getElementById("tools-list"),
    chatsToggle: document.getElementById("chats-toggle"),
    chatsToggleLabel: document.getElementById("chats-toggle-label"),
    chatsChevron: document.getElementById("chats-chevron"),
    chatsCount: document.getElementById("chats-count"),
    chatsPanel: document.getElementById("chats-panel"),
    chatsLoading: document.getElementById("chats-loading"),
    ctxRing: document.getElementById("ctx-ring"),
    ctxPct: document.getElementById("ctx-pct"),
    ctxTokens: document.getElementById("ctx-tokens"),
    ctxSub: document.getElementById("ctx-sub"),
    ctxMini: document.getElementById("ctx-mini"),
    ctxMiniRing: document.getElementById("ctx-mini-ring"),
    ctxMiniText: document.getElementById("ctx-mini-text"),
    gpuMeter: document.getElementById("gpu-meter"),
    gpuName: document.getElementById("gpu-name"),
    gpuCapacity: document.getElementById("gpu-capacity"),
    gpuBarWeights: document.getElementById("gpu-bar-weights"),
    gpuBarContext: document.getElementById("gpu-bar-context"),
    gpuBarOther: document.getElementById("gpu-bar-other"),
    gpuVramLabel: document.getElementById("gpu-vram-label"),
    gpuLoading: document.getElementById("gpu-loading"),
    ctxLoading: document.getElementById("ctx-loading"),
    modelLoading: document.getElementById("model-loading"),
    cwdLoading: document.getElementById("cwd-loading"),
    toolsLoading: document.getElementById("tools-loading"),
    projectName: document.getElementById("project-name"),
    btnOpenProject: document.getElementById("btn-open-project"),
    btnExplorerRefresh: document.getElementById("btn-explorer-refresh"),
    fileExplorer: document.getElementById("file-explorer"),
    fileExplorerWrap: document.getElementById("file-explorer-wrap"),
    fileExplorerEmpty: document.getElementById("file-explorer-empty"),
    fileExplorerLoading: document.getElementById("file-explorer-loading"),
    explorerViewToggle: document.getElementById("explorer-view-toggle"),
    explorerPanel: document.getElementById("explorer-panel"),
    workspacePanel: document.getElementById("workspace-panel"),
    chatPanel: document.getElementById("chat-panel"),
    resizeExplorer: document.getElementById("resize-explorer"),
    resizeChat: document.getElementById("resize-chat"),
    editorPane: document.getElementById("editor-pane"),
    editorTitle: document.getElementById("editor-title"),
    editorTabbarWrap: document.getElementById("editor-tabbar-wrap"),
    editorTabbar: document.getElementById("editor-tabbar"),
    editorEmpty: document.getElementById("editor-empty"),
    editorLoading: document.getElementById("editor-loading"),
    editorError: document.getElementById("editor-error"),
    editorCodeWrap: document.getElementById("editor-code-wrap"),
    editorLines: document.getElementById("editor-lines"),
    editorMinimap: document.getElementById("editor-minimap"),
    editorMinimapLines: document.getElementById("editor-minimap-lines"),
    editorMinimapViewport: document.getElementById("editor-minimap-viewport"),
    editorStatusLines: document.getElementById("editor-status-lines"),
    editorStatusLang: document.getElementById("editor-status-lang"),
    editorImageWrap: document.getElementById("editor-image-wrap"),
    editorImage: document.getElementById("editor-image"),
    projectPathDialog: document.getElementById("project-path-dialog"),
    projectPathBackdrop: document.getElementById("project-path-backdrop"),
    projectPathInput: document.getElementById("project-path-input"),
    projectPathError: document.getElementById("project-path-error"),
    projectPathCancel: document.getElementById("project-path-cancel"),
    projectPathConfirm: document.getElementById("project-path-confirm"),
    lightbox: document.getElementById("image-lightbox"),
    lightboxBackdrop: document.getElementById("image-lightbox-backdrop"),
    lightboxClose: document.getElementById("image-lightbox-close"),
    lightboxImg: document.getElementById("image-lightbox-img"),
    lightboxCaption: document.getElementById("image-lightbox-caption"),
  };

  function folderIconSvg() {
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="h-4 w-4 text-amber-500" aria-hidden="true">' +
      '<path d="M19.5 19.5H4.5a1.5 1.5 0 0 1-1.5-1.5V6.75A1.5 1.5 0 0 1 4.5 5.25h4.086a1.5 1.5 0 0 0 1.06-.44L10.94 3.72a1.5 1.5 0 0 1 1.06-.44h5.4a1.5 1.5 0 0 1 1.5 1.5v13.22a1.5 1.5 0 0 1-1.5 1.5Z" />' +
      "</svg>"
    );
  }

  function fileIconSvg() {
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" class="h-4 w-4 text-slate-400" aria-hidden="true">' +
      '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" stroke-linejoin="round" />' +
      '<path d="M14 3v5h5" stroke-linejoin="round" />' +
      "</svg>"
    );
  }

  function chevronIconSvg() {
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="h-3.5 w-3.5" aria-hidden="true">' +
      '<path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clip-rule="evenodd" />' +
      "</svg>"
    );
  }

  function readExplorerViewMode() {
    try {
      const stored = localStorage.getItem(EXPLORER_VIEW_STORAGE_KEY);
      return stored === "test" ? "test" : "all";
    } catch {
      return "all";
    }
  }

  function storeExplorerViewMode(mode) {
    try {
      localStorage.setItem(EXPLORER_VIEW_STORAGE_KEY, mode);
    } catch {
      /* ignore quota / private mode */
    }
  }

  function sortExplorerEntries(entries) {
    return [...entries].sort((a, b) => {
      const aDir = a.kind === "dir" ? 0 : 1;
      const bDir = b.kind === "dir" ? 0 : 1;
      if (aDir !== bDir) return aDir - bDir;
      return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    });
  }

  function filterExplorerEntries(entries, parentPath) {
    const filtered =
      state.explorerViewMode !== "test" || parentPath !== ""
        ? entries
        : entries.filter(
            (entry) => entry.kind === "dir" && EXPLORER_TEST_MODE_DIRS.has(entry.name)
          );
    return sortExplorerEntries(filtered);
  }

  function isExplorerPathVisible(relativePath) {
    if (state.explorerViewMode !== "test") return true;
    if (!relativePath) return true;
    const top = relativePath.replace(/\\/g, "/").split("/")[0];
    return EXPLORER_TEST_MODE_DIRS.has(top);
  }

  function syncExplorerViewToggle() {
    if (!els.explorerViewToggle) return;
    for (const btn of els.explorerViewToggle.querySelectorAll("[data-view]")) {
      const active = btn.dataset.view === state.explorerViewMode;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  function setExplorerViewMode(mode) {
    const next = mode === "test" ? "test" : "all";
    if (state.explorerViewMode === next) return;
    state.explorerViewMode = next;
    storeExplorerViewMode(next);
    if (state.explorerSelected && !isExplorerPathVisible(state.explorerSelected)) {
      state.explorerSelected = null;
    }
    syncExplorerViewToggle();
    renderFileExplorer();
  }

  function applyProject(project, { entries } = {}) {
    const prevRoot = state.project?.root || null;
    const nextRoot = project?.root || null;
    const projectChanged = prevRoot !== nextRoot;

    state.project = project || null;
    if (!project) {
      state.explorerExpanded.clear();
      state.explorerEntries.clear();
      state.explorerSelected = null;
      if (els.projectName) {
        els.projectName.textContent = "No project";
        els.projectName.title = "No project open";
      }
      if (els.fileExplorerWrap) els.fileExplorerWrap.classList.add("hidden");
      if (els.fileExplorerEmpty) els.fileExplorerEmpty.classList.remove("hidden");
      if (els.fileExplorer) els.fileExplorer.innerHTML = "";
      if (els.btnExplorerRefresh) els.btnExplorerRefresh.classList.add("hidden");
      clearEditorTabs();
      return;
    }

    if (els.btnExplorerRefresh) els.btnExplorerRefresh.classList.remove("hidden");

    if (projectChanged) {
      state.explorerExpanded.clear();
      state.explorerEntries.clear();
      state.explorerSelected = null;
      clearEditorTabs();
    }

    if (els.projectName) {
      els.projectName.textContent = project.name || "Project";
      els.projectName.title = project.root || project.name || "";
    }
    if (els.fileExplorerEmpty) els.fileExplorerEmpty.classList.add("hidden");
    if (els.fileExplorerWrap) {
      els.fileExplorerWrap.classList.remove("hidden");
      els.fileExplorerWrap.classList.add("flex");
    }

    syncExplorerViewToggle();
    if (entries) {
      state.explorerEntries.set("", entries);
      state.explorerExpanded.add("");
      renderFileExplorer();
    } else {
      loadExplorerRoot().catch(() => {});
    }
  }

  async function fetchExplorerEntries(relativePath = "") {
    const qs = relativePath ? `?path=${encodeURIComponent(relativePath)}` : "";
    const data = await api(`/api/project/entries${qs}`);
    return data.entries || [];
  }

  function setExplorerRefreshBusy(busy) {
    if (!els.btnExplorerRefresh) return;
    els.btnExplorerRefresh.disabled = busy;
    els.btnExplorerRefresh.classList.toggle("is-spinning", busy);
  }

  async function refreshExplorer() {
    if (!state.project) return;
    setExplorerRefreshBusy(true);
    setExplorerLoading(true);
    try {
      const pathsToRefresh = new Set(state.explorerExpanded);
      pathsToRefresh.add("");
      state.explorerEntries.clear();
      await Promise.all(
        [...pathsToRefresh].map(async (path) => {
          const entries = await fetchExplorerEntries(path);
          state.explorerEntries.set(path, entries);
        })
      );
      renderFileExplorer();
    } catch (err) {
      els.logStatus.textContent = err.message || String(err);
    } finally {
      setExplorerLoading(false);
      setExplorerRefreshBusy(false);
    }
  }

  function shouldRefreshExplorerForToolEvents(toolEvents) {
    if (!toolEvents?.length) return false;
    return toolEvents.some(
      (ev) =>
        ev.ok !== false &&
        (ev.name === "write_file" || ev.name === "str_replace" || ev.name === "run_command")
    );
  }

  async function loadExplorerRoot() {
    if (!state.project) return;
    setExplorerLoading(true);
    try {
      const entries = await fetchExplorerEntries("");
      state.explorerEntries.set("", entries);
      if (!state.explorerExpanded.size) state.explorerExpanded.add("");
      renderFileExplorer();
    } finally {
      setExplorerLoading(false);
    }
  }

  function setExplorerLoading(loading) {
    state.explorerLoading = loading;
    setWidgetLoading(els.fileExplorerLoading, loading);
  }

  async function ensureFolderExpanded(relativePath) {
    if (state.explorerEntries.has(relativePath)) return;
    const entries = await fetchExplorerEntries(relativePath);
    state.explorerEntries.set(relativePath, entries);
  }

  async function toggleExplorerFolder(relativePath) {
    if (state.explorerExpanded.has(relativePath)) {
      state.explorerExpanded.delete(relativePath);
      renderFileExplorer();
      return;
    }
    setExplorerLoading(true);
    try {
      await ensureFolderExpanded(relativePath);
      state.explorerExpanded.add(relativePath);
      renderFileExplorer();
    } catch (err) {
      els.logStatus.textContent = err.message || String(err);
    } finally {
      setExplorerLoading(false);
    }
  }

  function renderExplorerNode(entry, depth) {
    const isDir = entry.kind === "dir";
    const expanded = isDir && state.explorerExpanded.has(entry.path);
    const selected = state.explorerSelected === entry.path;
    const openInEditor = !isDir && state.editorTabs.some((tab) => tab.path === entry.path);
    const row = document.createElement("div");
    row.className = "explorer-node";
    row.dataset.path = entry.path;
    row.dataset.kind = entry.kind;

    const line = document.createElement("div");
    line.className = `explorer-row${selected ? " is-selected" : ""}${openInEditor ? " is-editor-open" : ""}`;
    line.style.paddingLeft = `${depth * 0.75 + 0.25}rem`;
    line.title = entry.path;
    line.dataset.kind = entry.kind;

    if (!isDir) {
      line.draggable = true;
      line.addEventListener("dragstart", (e) => {
        state.explorerDragPath = entry.path;
        e.dataTransfer.setData(EXPLORER_PATH_MIME, entry.path);
        e.dataTransfer.setData("text/plain", entry.path);
        e.dataTransfer.effectAllowed = "copy";
      });
      line.addEventListener("dragend", () => {
        state.explorerDragPath = null;
      });
      line.addEventListener("dblclick", (e) => {
        e.preventDefault();
        e.stopPropagation();
        openEditorFile(entry.path);
      });
    }

    if (isDir) {
      const chevron = document.createElement("button");
      chevron.type = "button";
      chevron.className = `explorer-chevron${expanded ? " is-expanded" : ""}`;
      chevron.setAttribute("aria-label", expanded ? "Collapse folder" : "Expand folder");
      chevron.innerHTML = chevronIconSvg();
      chevron.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleExplorerFolder(entry.path).catch((err) => {
          els.logStatus.textContent = err.message || String(err);
        });
      });
      line.appendChild(chevron);
    } else {
      const spacer = document.createElement("span");
      spacer.className = "explorer-chevron is-hidden";
      spacer.innerHTML = chevronIconSvg();
      line.appendChild(spacer);
    }

    const icon = document.createElement("span");
    icon.className = "explorer-icon";
    icon.innerHTML = isDir ? folderIconSvg() : fileIconSvg();
    line.appendChild(icon);

    const name = document.createElement("span");
    name.className = "explorer-name";
    name.textContent = entry.name;
    name.title = entry.name;
    line.appendChild(name);

    line.addEventListener("click", () => {
      state.explorerSelected = entry.path;
      renderFileExplorer();
      if (isDir) {
        toggleExplorerFolder(entry.path).catch((err) => {
          els.logStatus.textContent = err.message || String(err);
        });
      }
    });

    row.appendChild(line);

    if (isDir && expanded) {
      const childrenWrap = document.createElement("div");
      childrenWrap.className = "explorer-children";
      const children = filterExplorerEntries(
        state.explorerEntries.get(entry.path) || [],
        entry.path
      );
      for (const child of children) {
        childrenWrap.appendChild(renderExplorerNode(child, depth + 1));
      }
      row.appendChild(childrenWrap);
    }

    return row;
  }

  function renderFileExplorer() {
    if (!els.fileExplorer || !state.project) return;
    els.fileExplorer.innerHTML = "";

    const rootRow = document.createElement("div");
    rootRow.className = "explorer-node";
    rootRow.dataset.path = "";
    rootRow.dataset.kind = "dir";

    const rootLine = document.createElement("div");
    const rootExpanded = state.explorerExpanded.has("");
    const rootSelected = state.explorerSelected === "";
    rootLine.className = `explorer-row${rootSelected ? " is-selected" : ""}`;
    rootLine.style.paddingLeft = "0.25rem";
    rootLine.title = state.project.root || state.project.name || "";

    const rootChevron = document.createElement("button");
    rootChevron.type = "button";
    rootChevron.className = `explorer-chevron${rootExpanded ? " is-expanded" : ""}`;
    rootChevron.setAttribute("aria-label", rootExpanded ? "Collapse project root" : "Expand project root");
    rootChevron.innerHTML = chevronIconSvg();
    rootChevron.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleExplorerFolder("").catch((err) => {
        els.logStatus.textContent = err.message || String(err);
      });
    });
    rootLine.appendChild(rootChevron);

    const rootIcon = document.createElement("span");
    rootIcon.className = "explorer-icon";
    rootIcon.innerHTML = folderIconSvg();
    rootLine.appendChild(rootIcon);

    const rootName = document.createElement("span");
    rootName.className = "explorer-name font-medium";
    rootName.textContent = state.project.name || "Project";
    rootName.title = state.project.name || state.project.root || "Project";
    rootLine.appendChild(rootName);

    rootLine.addEventListener("click", () => {
      state.explorerSelected = "";
      renderFileExplorer();
    });
    rootRow.appendChild(rootLine);

    if (rootExpanded) {
      const childrenWrap = document.createElement("div");
      childrenWrap.className = "explorer-children";
      const children = filterExplorerEntries(state.explorerEntries.get("") || [], "");
      for (const child of children) {
        childrenWrap.appendChild(renderExplorerNode(child, 1));
      }
      rootRow.appendChild(childrenWrap);
    }

    els.fileExplorer.appendChild(rootRow);
  }

  function showProjectPathDialog(initialPath = "") {
    if (!els.projectPathDialog) return Promise.resolve(null);
    return new Promise((resolve) => {
      els.projectPathInput.value = initialPath || "";
      els.projectPathError.classList.add("hidden");
      els.projectPathError.textContent = "";
      els.projectPathDialog.classList.remove("hidden");
      els.projectPathDialog.classList.add("flex");
      els.projectPathInput.focus();
      els.projectPathInput.select();

      const cleanup = (value) => {
        els.projectPathDialog.classList.add("hidden");
        els.projectPathDialog.classList.remove("flex");
        els.projectPathConfirm.removeEventListener("click", onConfirm);
        els.projectPathCancel.removeEventListener("click", onCancel);
        els.projectPathBackdrop.removeEventListener("click", onCancel);
        document.removeEventListener("keydown", onKeydown);
        resolve(value);
      };

      const onConfirm = () => {
        const value = els.projectPathInput.value.trim();
        if (!value) {
          els.projectPathError.textContent = "Enter a folder path.";
          els.projectPathError.classList.remove("hidden");
          return;
        }
        cleanup(value);
      };

      const onCancel = () => cleanup(null);

      const onKeydown = (e) => {
        if (e.key === "Escape") onCancel();
        if (e.key === "Enter") onConfirm();
      };

      els.projectPathConfirm.addEventListener("click", onConfirm);
      els.projectPathCancel.addEventListener("click", onCancel);
      els.projectPathBackdrop.addEventListener("click", onCancel);
      document.addEventListener("keydown", onKeydown);
    });
  }

  async function openProjectAtPath(path) {
    const data = await api("/api/project/open", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    applyProject(data.project, { entries: data.entries || [] });
    if (data.cwd) els.statusCwd.textContent = data.cwd;
    els.logStatus.textContent = "";
  }

  async function browseAndOpenProject() {
    if (state.busy) return;
    els.logStatus.textContent = "";
    let selectedPath = null;
    try {
      const data = await api("/api/project/browse", {
        method: "POST",
        body: JSON.stringify({
          initial_path: state.project?.root || null,
        }),
      });
      selectedPath = data.path;
    } catch (err) {
      const cancelled =
        /cancel/i.test(String(err.message || "")) ||
        String(err.message || "").includes("400");
      if (!cancelled) {
        els.logStatus.textContent = err.message || String(err);
      }
    }

    if (!selectedPath) {
      selectedPath = await showProjectPathDialog(state.project?.root || "");
    }
    if (!selectedPath) return;

    setExplorerLoading(true);
    try {
      await openProjectAtPath(selectedPath);
    } catch (err) {
      els.projectPathError.textContent = err.message || String(err);
      els.projectPathError.classList.remove("hidden");
      const retry = await showProjectPathDialog(selectedPath);
      if (retry) await openProjectAtPath(retry);
    } finally {
      setExplorerLoading(false);
    }
  }

  function openImageLightbox({ src, alt = "", caption = "" }) {
    if (!els.lightbox || !els.lightboxImg || !src) return;
    els.lightboxImg.src = src;
    els.lightboxImg.alt = alt;
    if (els.lightboxCaption) {
      if (caption) {
        els.lightboxCaption.textContent = caption;
        els.lightboxCaption.classList.remove("hidden");
      } else {
        els.lightboxCaption.textContent = "";
        els.lightboxCaption.classList.add("hidden");
      }
    }
    els.lightbox.classList.remove("hidden");
    els.lightbox.classList.add("flex");
    document.body.classList.add("overflow-hidden");
    els.lightboxClose?.focus();
  }

  function closeImageLightbox() {
    if (!els.lightbox || !els.lightboxImg) return;
    els.lightbox.classList.add("hidden");
    els.lightbox.classList.remove("flex");
    els.lightboxImg.removeAttribute("src");
    els.lightboxImg.alt = "";
    if (els.lightboxCaption) {
      els.lightboxCaption.textContent = "";
      els.lightboxCaption.classList.add("hidden");
    }
    document.body.classList.remove("overflow-hidden");
  }

  function handleImageLightboxClick(e) {
    const btn = e.target.closest(".md-image-preview-btn");
    if (!btn) return;
    openImageLightbox({
      src: btn.dataset.lightboxSrc,
      alt: btn.dataset.lightboxAlt || "",
      caption: btn.dataset.lightboxCaption || "",
    });
  }

  function setWidgetLoading(el, loading) {
    if (!el) return;
    el.classList.toggle("hidden", !loading);
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function safeHref(url) {
    const u = String(url || "").trim();
    if (/^(https?:|mailto:|#|\/)/i.test(u)) return escapeHtml(u);
    return "#";
  }

  function safeSrc(url) {
    const u = String(url || "").trim().replace(/^["']|["']$/g, "");
    if (/^https?:\/\//i.test(u)) return escapeHtml(u);
    if (/^data:image\//i.test(u)) return escapeHtml(u);
    if (u.startsWith("/")) return escapeHtml(u);
    if (
      /^[a-zA-Z]:[\\/]/.test(u) ||
      u.startsWith("\\\\") ||
      u.startsWith("//") ||
      u.startsWith("~/") ||
      u.startsWith("~\\")
    ) {
      return escapeHtml(`/api/local-file?path=${encodeURIComponent(u)}`);
    }
    if (/[\\/]/.test(u)) {
      return escapeHtml(`/api/local-file?path=${encodeURIComponent(u)}`);
    }
    return "";
  }

  function parseImageTarget(inner) {
    let body = String(inner || "").trim();
    let url = body;
    let title = "";

    if (body.startsWith("<") && body.includes(">")) {
      const end = body.indexOf(">");
      url = body.slice(1, end);
      const rest = body.slice(end + 1).trim();
      const titleMatch = rest.match(/^"([^"]*)"$/);
      if (titleMatch) title = titleMatch[1];
    } else {
      const titleMatch = body.match(/^([\s\S]+?)\s+"([^"]*)"\s*$/);
      if (titleMatch) {
        url = titleMatch[1].trim();
        title = titleMatch[2];
      }
    }

    url = url.trim().replace(/^["']|["']$/g, "");
    return url ? { url, title } : null;
  }

  function parseImageAt(text, start) {
    if (String(text || "").slice(start, start + 2) !== "![") return null;
    const altEnd = text.indexOf("]", start + 2);
    if (altEnd === -1 || text[altEnd + 1] !== "(") return null;
    const alt = text.slice(start + 2, altEnd);
    let depth = 0;
    let j = altEnd + 2;
    for (; j < text.length; j++) {
      const ch = text[j];
      if (ch === "(") depth += 1;
      else if (ch === ")") {
        if (depth === 0) break;
        depth -= 1;
      }
    }
    if (j >= text.length) return null;
    const target = parseImageTarget(text.slice(altEnd + 2, j));
    if (!target) return null;
    return {
      alt,
      url: target.url,
      title: target.title || "",
      endIndex: j + 1,
    };
  }

  function extractMarkdownImages(text) {
    const images = [];
    let out = "";
    let i = 0;
    while (i < text.length) {
      const hit = text.indexOf("![", i);
      if (hit === -1) {
        out += text.slice(i);
        break;
      }
      out += text.slice(i, hit);
      const parsed = parseImageAt(text, hit);
      if (!parsed) {
        out += text[hit];
        i = hit + 1;
        continue;
      }
      const idx = images.length;
      images.push(parsed);
      out += `\x00IMG${idx}\x00`;
      i = parsed.endIndex;
    }
    return { text: out, images };
  }

  function parseImageMarkdown(raw) {
    const trimmed = String(raw || "").trim();
    const parsed = parseImageAt(trimmed, 0);
    if (!parsed || parsed.endIndex !== trimmed.length) return null;
    return { alt: parsed.alt, url: parsed.url, title: parsed.title };
  }

  function parseCaptionLine(line) {
    const trimmed = String(line || "").trim();
    if (!trimmed) return "";
    const pandoc = trimmed.match(/^:\s+(.+)$/);
    if (pandoc) return pandoc[1];
    const italic = trimmed.match(/^(\*[^*\n]+\*|_[^_\n]+_)$/);
    if (italic) return italic[1].slice(1, -1);
    if (/^Figure\s+\d+[:.]?\s/i.test(trimmed)) return trimmed;
    return "";
  }

  function findFollowingCaption(lines, startIndex) {
    let i = startIndex;
    while (i < lines.length && !lines[i].trim()) i++;
    if (i >= lines.length) return null;
    const caption = parseCaptionLine(lines[i]);
    if (!caption) return null;
    return { caption, nextIndex: i + 1 };
  }

  function renderImageMarkup(src, alt, { caption = "", block = false } = {}) {
    const safe = safeSrc(src);
    if (!safe) return escapeHtml(`![${alt}](${src})`);
    const altAttr = escapeHtml(alt || "");
    const imgClass = block ? "md-image md-image-block" : "md-image md-image-inline";
    const img = `<img src="${safe}" alt="${altAttr}" loading="lazy" class="${imgClass}" />`;
    const capHtml = caption
      ? `<figcaption>${formatInline(caption)}</figcaption>`
      : "";
    if (!block && !caption) return img;
    if (block) {
      const capData = caption
        ? ` data-lightbox-caption="${escapeHtml(caption)}"`
        : "";
      const label = alt ? `View full image: ${altAttr}` : "View full image";
      return (
        `<figure class="md-figure">` +
        `<button type="button" class="md-image-preview-btn" data-lightbox-src="${safe}" data-lightbox-alt="${altAttr}"${capData} aria-label="${label}">${img}</button>` +
        `${capHtml}</figure>`
      );
    }
    return `<figure class="md-figure">${img}${capHtml}</figure>`;
  }

  function parseTableCells(line) {
    let trimmed = line.trim();
    if (trimmed.startsWith("|")) trimmed = trimmed.slice(1);
    if (trimmed.endsWith("|")) trimmed = trimmed.slice(0, -1);
    return trimmed.split("|").map((cell) => cell.trim());
  }

  function isTableSeparator(line) {
    return /^\|?\s*(:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/.test(String(line || "").trim());
  }

  function isTableRow(line) {
    const trimmed = String(line || "").trim();
    return trimmed.includes("|") && !isTableSeparator(trimmed);
  }

  function renderTable(headerLine, separatorLine, bodyLines) {
    const headers = parseTableCells(headerLine);
    const alignments = parseTableCells(separatorLine).map((cell) => {
      const inner = cell.replace(/-/g, "").trim();
      if (inner.startsWith(":") && inner.endsWith(":")) return "center";
      if (inner.endsWith(":")) return "right";
      if (inner.startsWith(":")) return "left";
      return "";
    });

    const headHtml = headers
      .map((cell, idx) => {
        const align = alignments[idx]
          ? ` style="text-align:${alignments[idx]}"`
          : "";
        return `<th${align}>${formatInline(cell)}</th>`;
      })
      .join("");

    const bodyHtml = bodyLines
      .map((rowLine) => {
        const cells = parseTableCells(rowLine);
        return `<tr>${cells
          .map((cell, idx) => {
            const align = alignments[idx]
              ? ` style="text-align:${alignments[idx]}"`
              : "";
            return `<td${align}>${formatInline(cell)}</td>`;
          })
          .join("")}</tr>`;
      })
      .join("");

    return (
      '<div class="md-table-wrap">' +
      "<table>" +
      `<thead><tr>${headHtml}</tr></thead>` +
      (bodyHtml ? `<tbody>${bodyHtml}</tbody>` : "") +
      "</table></div>"
    );
  }

  function isImageLine(line) {
    return parseImageMarkdown(line) != null;
  }

  function isDisplayMathLine(line) {
    return String(line || "").trim().startsWith("$$");
  }

  function renderKatex(tex, displayMode) {
    const source = String(tex || "").trim();
    if (!source) return "";
    if (typeof katex === "undefined") {
      return displayMode
        ? `<pre class="math-fallback">${escapeHtml(source)}</pre>`
        : `<code>${escapeHtml(source)}</code>`;
    }
    try {
      return katex.renderToString(source, {
        displayMode,
        throwOnError: false,
        strict: "ignore",
      });
    } catch (_) {
      return escapeHtml(source);
    }
  }

  function parseDisplayMathBlock(lines, startIndex) {
    const first = lines[startIndex].trim();
    if (!first.startsWith("$$")) return null;

    if (first.endsWith("$$") && first.length > 4) {
      return { tex: first.slice(2, -2), nextIndex: startIndex + 1 };
    }

    let tex = first.slice(2);
    let i = startIndex + 1;
    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();
      if (trimmed.endsWith("$$")) {
        const last = trimmed.slice(0, -2);
        if (last) tex += (tex ? "\n" : "") + last;
        return { tex, nextIndex: i + 1 };
      }
      tex += (tex ? "\n" : "") + line;
      i++;
    }

    return { tex, nextIndex: i, incomplete: true };
  }

  function isBlockStart(line, lines, index) {
    const trimmed = line.trim();
    return (
      /^(#{1,6})\s+/.test(line) ||
      /^(\*\*\*|---|___)\s*$/.test(trimmed) ||
      /^>\s?/.test(line) ||
      /^[-*+]\s+/.test(line) ||
      /^\d+\.\s+/.test(line) ||
      isImageLine(line) ||
      isDisplayMathLine(line) ||
      (lines != null &&
        index != null &&
        isTableRow(line) &&
        index + 1 < lines.length &&
        isTableSeparator(lines[index + 1]))
    );
  }

  function renderMarkdown(src) {
    const text = String(src || "");
    const parts = [];
    let last = 0;
    const fence = /```([\w-]*)\n?([\s\S]*?)```/g;
    let match;
    while ((match = fence.exec(text)) !== null) {
      if (match.index > last) {
        parts.push({ type: "text", value: text.slice(last, match.index) });
      }
      parts.push({ type: "code", lang: match[1] || "", value: match[2] });
      last = match.index + match[0].length;
    }
    if (last < text.length) {
      parts.push({ type: "text", value: text.slice(last) });
    }
    if (!parts.length) parts.push({ type: "text", value: text });

    return parts
      .map((part) => {
        if (part.type === "code") {
          const lang = part.lang ? ` data-lang="${escapeHtml(part.lang)}"` : "";
          return `<pre${lang}><code>${escapeHtml(part.value.replace(/\n$/, ""))}</code></pre>`;
        }
        return parseBlocks(part.value);
      })
      .join("");
  }

  function parseBlocks(text) {
    const lines = String(text || "").split("\n");
    const html = [];
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();

      if (!trimmed) {
        i++;
        continue;
      }

      if (/^(\*\*\*|---|___)\s*$/.test(trimmed)) {
        html.push("<hr />");
        i++;
        continue;
      }

      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        const level = heading[1].length;
        html.push(`<h${level}>${formatInline(heading[2])}</h${level}>`);
        i++;
        continue;
      }

      if (/^>\s?/.test(line)) {
        const quoteLines = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) {
          quoteLines.push(lines[i].replace(/^>\s?/, ""));
          i++;
        }
        html.push(`<blockquote>${parseBlocks(quoteLines.join("\n"))}</blockquote>`);
        continue;
      }

      if (/^[-*+]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^[-*+]\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^[-*+]\s+/, ""));
          i++;
        }
        html.push(
          `<ul>${items.map((item) => `<li>${formatInline(item)}</li>`).join("")}</ul>`
        );
        continue;
      }

      if (/^\d+\.\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\d+\.\s+/, ""));
          i++;
        }
        html.push(
          `<ol>${items.map((item) => `<li>${formatInline(item)}</li>`).join("")}</ol>`
        );
        continue;
      }

      if (isTableRow(line) && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
        const headerLine = line;
        const separatorLine = lines[i + 1];
        i += 2;
        const bodyLines = [];
        while (i < lines.length && isTableRow(lines[i])) {
          bodyLines.push(lines[i]);
          i++;
        }
        html.push(renderTable(headerLine, separatorLine, bodyLines));
        continue;
      }

      if (isDisplayMathLine(line)) {
        const block = parseDisplayMathBlock(lines, i);
        if (block) {
          if (block.incomplete) {
            html.push(`<p>${escapeHtml("$$" + block.tex)}</p>`);
          } else {
            html.push(`<div class="md-math-block">${renderKatex(block.tex, true)}</div>`);
          }
          i = block.nextIndex;
          continue;
        }
      }

      const image = parseImageMarkdown(line);
      if (image) {
        let caption = image.title;
        let nextIndex = i + 1;
        if (!caption) {
          const following = findFollowingCaption(lines, nextIndex);
          if (following) {
            caption = following.caption;
            nextIndex = following.nextIndex;
          } else if (image.alt) {
            caption = image.alt;
          }
        }
        html.push(renderImageMarkup(image.url, image.alt, { caption, block: true }));
        i = nextIndex;
        continue;
      }

      const para = [];
      while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i], lines, i)) {
        para.push(lines[i]);
        i++;
      }
      if (para.length) {
        html.push(`<p>${formatInline(para.join("\n"))}</p>`);
      }
    }

    return html.join("");
  }

  function formatInline(text) {
    const codes = [];
    const inlineMath = [];
    let out = String(text || "");

    out = out.replace(/`([^`\n]+)`/g, (_, code) => {
      const idx = codes.length;
      codes.push(code);
      return `\x00CODE${idx}\x00`;
    });

    const imageExtract = extractMarkdownImages(out);
    out = imageExtract.text;
    const images = imageExtract.images;

    out = out.replace(/(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)/g, (_, tex) => {
      const idx = inlineMath.length;
      inlineMath.push(tex);
      return `\x00MATH${idx}\x00`;
    });

    out = escapeHtml(out);

    out = out.replace(
      /(?<!!)\[([^\]]+)\]\(([^)]+)\)/g,
      (_, label, url) =>
        `<a href="${safeHref(url)}" target="_blank" rel="noopener noreferrer">${label}</a>`
    );

    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    out = out.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
    out = out.replace(/_([^_\n]+)_/g, "<em>$1</em>");
    out = out.replace(/~~([^~]+)~~/g, "<s>$1</s>");

    out = out.replace(/\x00CODE(\d+)\x00/g, (_, idx) => `<code>${codes[idx]}</code>`);
    out = out.replace(
      /\x00MATH(\d+)\x00/g,
      (_, idx) => `<span class="md-math-inline">${renderKatex(inlineMath[idx], false)}</span>`
    );
    out = out.replace(/\x00IMG(\d+)\x00/g, (_, idx) => {
      const img = images[idx];
      return renderImageMarkup(img.url, img.alt, { caption: img.title, block: false });
    });
    out = out.replace(/\n/g, "<br />");
    return out;
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const data = await res.json();
        detail = data.detail || detail;
      } catch (_) {
        /* ignore */
      }
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    if (res.status === 204) return null;
    return res.json();
  }

  function focusComposer() {
    if (!els.composer || state.busy) return;
    requestAnimationFrame(() => {
      if (!state.busy && els.composer) els.composer.focus();
    });
  }

  let composerStatusTimer = null;

  function hideComposerStatus() {
    if (composerStatusTimer) {
      clearTimeout(composerStatusTimer);
      composerStatusTimer = null;
    }
    if (!els.composerStatus) return;
    els.composerStatus.classList.add("hidden");
  }

  function showComposerStatus(message, kind = "error") {
    if (!els.composerStatus) return;
    if (!message) {
      hideComposerStatus();
      return;
    }
    if (composerStatusTimer) clearTimeout(composerStatusTimer);

    const icon = kind === "success" ? "✓" : kind === "warning" ? "!" : "✕";
    els.composerStatus.className = `composer-status-${kind}`;
    els.composerStatus.classList.remove("hidden");
    const iconEl = els.composerStatus.querySelector(".composer-status-icon");
    const textEl = els.composerStatus.querySelector(".composer-status-text");
    if (iconEl) iconEl.textContent = icon;
    if (textEl) textEl.textContent = message;

    const delay = kind === "success" ? 3500 : 8000;
    composerStatusTimer = setTimeout(hideComposerStatus, delay);
  }

  function isAbsoluteFilesystemPath(value) {
    const text = String(value || "").trim();
    return /^([a-zA-Z]:[\\/]|\\\\|\/)/.test(text);
  }

  function isExplorerDrag(dataTransfer) {
    if (state.explorerDragPath) return true;
    const types = dataTransfer?.types ? Array.from(dataTransfer.types) : [];
    return types.includes(EXPLORER_PATH_MIME);
  }

  function resolveExplorerDropPath(dataTransfer) {
    const fromMime = dataTransfer.getData(EXPLORER_PATH_MIME);
    const fromState = state.explorerDragPath;
    const fromPlain = dataTransfer.getData("text/plain");
    const candidates = [fromMime, fromState];
    // text/plain from OS drops is often just a filename or an absolute path —
    // only trust it for drags that originated in our project explorer.
    if (isExplorerDrag(dataTransfer)) {
      candidates.push(fromPlain);
    }
    for (const candidate of candidates) {
      const normalized = String(candidate || "").replace(/\\/g, "/").trim();
      if (!normalized || isAbsoluteFilesystemPath(normalized)) continue;
      return normalized;
    }
    return "";
  }

  function setBusy(busy) {
    const wasBusy = state.busy;
    state.busy = busy;
    els.composer.disabled = busy;
    els.btnSend.disabled = busy;
    els.btnStop.disabled = !busy;
    // Labels aren't form controls; disable the underlying file inputs instead.
    els.inputImage.disabled = busy;
    els.inputFile.disabled = busy;
    els.btnAttachImage.classList.toggle("pointer-events-none", busy);
    els.btnAttachImage.classList.toggle("opacity-40", busy);
    els.btnAttachFile.classList.toggle("pointer-events-none", busy);
    els.btnAttachFile.classList.toggle("opacity-40", busy);
    if (els.btnSkills) {
      els.btnSkills.disabled = busy;
      els.btnSkills.classList.toggle("pointer-events-none", busy);
      els.btnSkills.classList.toggle("opacity-40", busy);
    }
    if (busy) setSkillsMenuOpen(false);
    els.composer.placeholder = busy ? "Waiting for model…" : "Message…";
    if (busy) {
      els.statusText.textContent = "Working…";
      els.statusDot.className = "h-1.5 w-1.5 rounded-full bg-accent animate-pulseSoft";
      els.statusPill.className =
        "inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent";
      startActivityTimer();
    } else {
      els.statusText.textContent = "Ready";
      els.statusDot.className = "h-1.5 w-1.5 rounded-full bg-emerald-500";
      els.statusPill.className =
        "inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600";
      stopActivityTimer();
      state.requestStartedAt = null;
    }
    // Refresh bubbles so the typing indicator appears/clears with busy state.
    if (state.messages.length) syncMessages();
    if (wasBusy && !busy) focusComposer();
  }

  function fileExt(name) {
    const base = String(name || "").split(/[/\\]/).pop() || "";
    const dot = base.lastIndexOf(".");
    return dot >= 0 ? base.slice(dot).toLowerCase() : "";
  }

  function projectFileKind(name) {
    const ext = fileExt(name);
    if (IMAGE_EXTS.has(ext)) return "image";
    if (FILE_EXTS.has(ext)) return "text";
    return null;
  }

  const LANG_BY_EXT = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TSX",
    ".jsx": "JSX",
    ".json": "JSON",
    ".jsonc": "JSON",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hxx": "C++",
    ".c": "C",
    ".h": "C",
    ".swift": "Swift",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dockerfile": "Dockerfile",
  };

  const HLJS_LANG_BY_EXT = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".json": "json",
    ".jsonc": "json",
    ".html": "xml",
    ".htm": "xml",
    ".css": "css",
    ".scss": "scss",
    ".sass": "scss",
    ".less": "less",
    ".md": "markdown",
    ".markdown": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "ini",
    ".xml": "xml",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".ps1": "powershell",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".swift": "swift",
    ".vue": "xml",
    ".svelte": "xml",
    ".dockerfile": "dockerfile",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".env": "bash",
  };

  function editorHljsLanguage(name) {
    const ext = fileExt(name);
    if (HLJS_LANG_BY_EXT[ext]) return HLJS_LANG_BY_EXT[ext];
    const base = String(name || "").split(/[/\\]/).pop() || "";
    if (base.toLowerCase() === "dockerfile") return "dockerfile";
    if (base.toLowerCase() === "makefile") return "makefile";
    return "plaintext";
  }

  function projectFileUrl(relativePath) {
    const rel = String(relativePath || "").replace(/\\/g, "/").trim();
    return `/api/project/file?path=${encodeURIComponent(rel)}`;
  }

  function revokeEditorTabImage(tab) {
    if (tab?.kind === "image" && tab.imageUrl?.startsWith("blob:")) {
      URL.revokeObjectURL(tab.imageUrl);
      tab.imageUrl = null;
    }
  }

  async function fetchProjectFile(relativePath) {
    const res = await fetch(projectFileUrl(relativePath), { cache: "no-store" });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return res;
  }

  function findEditorTab(path) {
    if (!path) return null;
    const direct = state.editorTabs.find((tab) => tab.path === path);
    if (direct) return direct;
    const lower = path.toLowerCase();
    return state.editorTabs.find((tab) => tab.path.toLowerCase() === lower) || null;
  }

  function clearEditorTabs() {
    for (const tab of state.editorTabs) revokeEditorTabImage(tab);
    state.editorTabs = [];
    state.editorActivePath = null;
    state.editorPath = null;
    showEditorEmpty();
  }

  function syncEditorHeader() {
    const active = state.editorActivePath ? findEditorTab(state.editorActivePath) : null;
    if (els.editorTitle) {
      els.editorTitle.textContent = active?.name || "No file open";
      els.editorTitle.title = active?.path || "No file open";
    }
    if (els.editorTabbarWrap) {
      els.editorTabbarWrap.classList.toggle("hidden", state.editorTabs.length === 0);
    }
  }

  function renderEditorTabs() {
    if (!els.editorTabbar) return;
    els.editorTabbar.innerHTML = "";

    for (const tab of state.editorTabs) {
      const tabEl = document.createElement("div");
      tabEl.className = `editor-tab${tab.path === state.editorActivePath ? " is-active" : ""}`;
      tabEl.setAttribute("role", "tab");
      tabEl.setAttribute("tabindex", tab.path === state.editorActivePath ? "0" : "-1");
      tabEl.setAttribute("aria-selected", tab.path === state.editorActivePath ? "true" : "false");
      tabEl.title = tab.path;
      tabEl.dataset.path = tab.path;

      const name = document.createElement("span");
      name.className = "editor-tab-name";
      name.textContent = tab.name;
      tabEl.appendChild(name);

      const close = document.createElement("button");
      close.type = "button";
      close.className = "editor-tab-close";
      close.setAttribute("aria-label", `Close ${tab.name}`);
      close.textContent = "×";
      close.addEventListener("click", (e) => {
        e.stopPropagation();
        closeEditorTab(tab.path);
      });
      tabEl.appendChild(close);

      tabEl.addEventListener("click", () => activateEditorTab(tab.path));
      tabEl.addEventListener("auxclick", (e) => {
        if (e.button !== 1) return;
        e.preventDefault();
        closeEditorTab(tab.path);
      });
      tabEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          activateEditorTab(tab.path);
        }
      });
      els.editorTabbar.appendChild(tabEl);
    }
    syncEditorHeader();
  }

  function activateEditorTab(path) {
    const tab = findEditorTab(path);
    if (!tab) return;

    state.editorActivePath = path;
    state.editorPath = path;
    hideEditorViews();

    if (tab.kind === "image") {
      if (els.editorImage) {
        els.editorImage.src = tab.imageUrl || "";
        els.editorImage.alt = tab.name;
      }
      if (els.editorImageWrap) els.editorImageWrap.classList.remove("hidden");
    } else {
      if (els.editorCodeWrap) els.editorCodeWrap.classList.remove("hidden");
      if (els.editorStatusLang) {
        els.editorStatusLang.textContent = editorLanguageLabel(tab.name);
      }
      renderEditorHighlight(tab.content || "", tab.name);
    }

    renderEditorTabs();
    renderFileExplorer();
  }

  function closeEditorTab(path) {
    const index = state.editorTabs.findIndex((tab) => tab.path === path);
    if (index < 0) return;

    const closing = state.editorTabs[index];
    revokeEditorTabImage(closing);
    state.editorTabs.splice(index, 1);

    if (state.editorActivePath === path) {
      if (state.editorTabs.length) {
        const next = state.editorTabs[Math.min(index, state.editorTabs.length - 1)];
        activateEditorTab(next.path);
      } else {
        clearEditorTabs();
      }
      return;
    }

    renderEditorTabs();
    renderFileExplorer();
  }

  function addEditorTextTab(relativePath, name, content) {
    const existing = findEditorTab(relativePath);
    if (existing) {
      existing.content = content;
      existing.name = name;
      existing.kind = "text";
      activateEditorTab(relativePath);
      return;
    }

    state.editorTabs.push({
      path: relativePath,
      name,
      kind: "text",
      content,
    });
    activateEditorTab(relativePath);
  }

  function addEditorImageTab(relativePath, name, objectUrl) {
    const existing = findEditorTab(relativePath);
    if (existing) {
      revokeEditorTabImage(existing);
      existing.imageUrl = objectUrl;
      existing.name = name;
      existing.kind = "image";
      activateEditorTab(relativePath);
      return;
    }

    state.editorTabs.push({
      path: relativePath,
      name,
      kind: "image",
      imageUrl: objectUrl,
    });
    activateEditorTab(relativePath);
  }

  function highlightEditorLine(line, language) {
    const source = line.length ? line : " ";
    if (!window.hljs) return escapeHtml(source);
    try {
      if (language !== "plaintext" && hljs.getLanguage(language)) {
        return hljs.highlight(source, { language }).value;
      }
      return hljs.highlightAuto(source).value;
    } catch {
      return escapeHtml(source);
    }
  }

  function renderEditorHighlight(content, name) {
    state.editorText = content;
    if (!els.editorLines) return;

    const language = editorHljsLanguage(name);
    const lines = content.split("\n");
    const lineCount = Math.max(lines.length, 1);
    const digits = String(lineCount).length;
    const gutterWidth = Math.max(2.75, 0.5 + digits * 0.55 + 0.75);

    const rows = lines.map((line, index) => {
      const highlighted = highlightEditorLine(line, language);
      return (
        `<div class="editor-line">` +
        `<div class="editor-line-num" style="min-width:${gutterWidth}rem">${index + 1}</div>` +
        `<div class="editor-line-code hljs">${highlighted}</div>` +
        `</div>`
      );
    });

    els.editorLines.innerHTML = rows.join("");

    if (els.editorStatusLines) {
      els.editorStatusLines.textContent =
        lineCount === 1 ? "1 line" : `${lineCount.toLocaleString()} lines`;
    }
    renderEditorMinimap(content, name);
    requestAnimationFrame(updateMinimapViewport);
  }

  const MINIMAP_MAX_LINES = 500;

  function minimapLinesForContent(content) {
    const lines = content.split("\n");
    if (lines.length <= MINIMAP_MAX_LINES) return lines;

    const sampled = new Array(MINIMAP_MAX_LINES);
    const last = lines.length - 1;
    for (let i = 0; i < MINIMAP_MAX_LINES; i++) {
      sampled[i] = lines[Math.min(last, Math.floor((i * lines.length) / MINIMAP_MAX_LINES))];
    }
    return sampled;
  }

  function renderEditorMinimap(content, _name) {
    if (!els.editorMinimap || !els.editorMinimapLines) return;
    const lines = minimapLinesForContent(content);
    const rows = new Array(lines.length);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const snippet = line.length > 160 ? `${line.slice(0, 160)}…` : line;
      rows[i] = `<div class="editor-minimap-line">${escapeHtml(snippet || " ")}</div>`;
    }
    els.editorMinimapLines.innerHTML = rows.join("");
    els.editorMinimap.classList.remove("hidden");
    els.editorMinimap.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => {
      fitMinimapScale();
      updateMinimapViewport();
    });
  }

  const MINIMAP_MAX_SCALE = 0.16;

  function fitMinimapScale() {
    if (!els.editorMinimap || !els.editorMinimapLines) return;
    const available = els.editorMinimap.clientHeight;
    const contentHeight = els.editorMinimapLines.scrollHeight;
    if (available <= 0 || contentHeight <= 0) return;

    // Always render at minimap scale — shrink long files to fit, never enlarge short ones.
    const fitScale = available / contentHeight;
    const scale = Math.min(MINIMAP_MAX_SCALE, fitScale);
    els.editorMinimapLines.style.transform = `scale(${scale})`;
    els.editorMinimapLines.style.width = `${100 / scale}%`;
  }

  function updateMinimapViewport() {
    const editor = els.editorLines;
    const minimap = els.editorMinimap;
    const viewport = els.editorMinimapViewport;
    if (!editor || !minimap || !viewport || minimap.classList.contains("hidden")) return;

    fitMinimapScale();

    const scrollHeight = editor.scrollHeight;
    const clientHeight = editor.clientHeight;
    const minimapHeight = minimap.clientHeight;

    if (scrollHeight <= clientHeight + 1 || minimapHeight <= 0) {
      viewport.classList.add("hidden");
      return;
    }

    viewport.classList.remove("hidden");
    const visibleRatio = clientHeight / scrollHeight;
    const viewportHeight = Math.max(visibleRatio * minimapHeight, 32);
    const maxScroll = scrollHeight - clientHeight;
    const scrollRatio = maxScroll > 0 ? editor.scrollTop / maxScroll : 0;
    const maxTop = minimapHeight - viewportHeight;
    viewport.style.height = `${viewportHeight}px`;
    viewport.style.top = `${scrollRatio * maxTop}px`;
  }

  function scrollEditorFromMinimap(clientY) {
    const minimap = els.editorMinimap;
    const editor = els.editorLines;
    if (!minimap || !editor) return;

    const rect = minimap.getBoundingClientRect();
    const y = Math.max(0, Math.min(rect.height, clientY - rect.top));
    const ratio = rect.height > 0 ? y / rect.height : 0;
    const maxScroll = Math.max(0, editor.scrollHeight - editor.clientHeight);
    editor.scrollTop = ratio * maxScroll;
    updateMinimapViewport();
  }

  function initEditorMinimap() {
    if (!els.editorLines || !els.editorMinimap) return;

    els.editorLines.addEventListener("scroll", updateMinimapViewport, { passive: true });

    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(() => updateMinimapViewport());
      ro.observe(els.editorLines);
      ro.observe(els.editorMinimap);
      if (els.editorCodeWrap) ro.observe(els.editorCodeWrap);
    } else {
      window.addEventListener("resize", updateMinimapViewport);
    }

    const finishDrag = () => {
      state.minimapDragging = false;
      els.editorMinimap.classList.remove("is-dragging");
    };

    els.editorMinimap.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      state.minimapDragging = true;
      els.editorMinimap.classList.add("is-dragging");
      els.editorMinimap.setPointerCapture(e.pointerId);
      scrollEditorFromMinimap(e.clientY);
    });

    els.editorMinimap.addEventListener("pointermove", (e) => {
      if (!state.minimapDragging) return;
      scrollEditorFromMinimap(e.clientY);
    });

    els.editorMinimap.addEventListener("pointerup", finishDrag);
    els.editorMinimap.addEventListener("pointercancel", finishDrag);
  }

  function editorLanguageLabel(name) {
    const ext = fileExt(name);
    if (LANG_BY_EXT[ext]) return LANG_BY_EXT[ext];
    if (ext) return ext.slice(1).toUpperCase();
    return "Plain text";
  }

  function setEditorLoading(loading) {
    setWidgetLoading(els.editorLoading, loading);
  }

  function hideEditorViews() {
    if (els.editorEmpty) els.editorEmpty.classList.add("hidden");
    if (els.editorError) els.editorError.classList.add("hidden");
    if (els.editorCodeWrap) els.editorCodeWrap.classList.add("hidden");
    if (els.editorImageWrap) els.editorImageWrap.classList.add("hidden");
  }

  function showEditorEmpty() {
    state.editorPath = null;
    state.editorActivePath = null;
    hideEditorViews();
    if (els.editorEmpty) els.editorEmpty.classList.remove("hidden");
    state.editorText = "";
    if (els.editorLines) els.editorLines.innerHTML = "";
    if (els.editorMinimap) {
      els.editorMinimap.classList.add("hidden");
      els.editorMinimap.setAttribute("aria-hidden", "true");
    }
    if (els.editorMinimapLines) els.editorMinimapLines.innerHTML = "";
    if (els.editorImage) els.editorImage.removeAttribute("src");
    renderEditorTabs();
    renderFileExplorer();
  }

  function showEditorError(message) {
    if (state.editorTabs.length && state.editorActivePath) {
      activateEditorTab(state.editorActivePath);
    } else {
      hideEditorViews();
      if (els.editorEmpty) els.editorEmpty.classList.remove("hidden");
    }
    if (els.editorError) {
      els.editorError.textContent = message;
      els.editorError.classList.remove("hidden");
    }
  }

  function normalizeRelativePath(rawPath) {
    if (!rawPath) return "";
    let p = String(rawPath).replace(/\\/g, "/").trim();
    p = p.replace(/^\.\//, "");
    if (state.project?.root) {
      let root = String(state.project.root).replace(/\\/g, "/").trim();
      if (root.endsWith("/")) root = root.slice(0, -1);
      if (p.toLowerCase().startsWith(root.toLowerCase() + "/")) {
        p = p.slice(root.length + 1);
      }
    }
    return p.replace(/^\/+/, "");
  }

  async function openEditorFile(relativePath, options = {}) {
    const rel = normalizeRelativePath(relativePath);
    if (!rel) return;
    if (!state.project) {
      showEditorError("Open a project to view files.");
      return;
    }

    const name = rel.split("/").pop() || rel;
    const existing = findEditorTab(rel);
    if (existing && !options.reload) {
      activateEditorTab(existing.path);
    }

    const kind = projectFileKind(name);
    if (!kind) {
      showEditorError(`Cannot open in editor: unsupported file type (${name}).`);
      return;
    }

    if (!existing) {
      hideEditorViews();
      setEditorLoading(true);
    }

    try {
      if (kind === "image") {
        const res = await fetchProjectFile(rel);
        const blob = await res.blob();
        const objectUrl = URL.createObjectURL(blob);
        if (existing) {
          revokeEditorTabImage(existing);
          existing.imageUrl = objectUrl;
          existing.name = name;
          existing.kind = "image";
          if (!options.keepActive || state.editorActivePath === existing.path) {
            activateEditorTab(existing.path);
          } else {
            renderEditorTabs();
          }
        } else {
          addEditorImageTab(rel, name, objectUrl);
        }
        return;
      }

      const res = await fetchProjectFile(rel);
      const blob = await res.blob();
      if (blob.size > MAX_TEXT_BYTES) {
        throw new Error(`File too large to open (max ${MAX_TEXT_BYTES / 1024} KB).`);
      }
      const text = await blob.text();
      if (existing) {
        existing.content = text;
        existing.name = name;
        existing.kind = "text";
        if (!options.keepActive || state.editorActivePath === existing.path) {
          activateEditorTab(existing.path);
        } else {
          renderEditorTabs();
        }
      } else {
        addEditorTextTab(rel, name, text);
      }
    } catch (err) {
      if (!options.keepActive || state.editorActivePath === rel || (existing && state.editorActivePath === existing.path)) {
        showEditorError(err.message || String(err));
      }
    } finally {
      if (!existing) {
        setEditorLoading(false);
      }
    }
  }

  async function reloadEditorTabsForToolEvents(toolEvents) {
    if (!toolEvents?.length || !state.project || !state.editorTabs.length) return;
    const pathsToReload = new Set();
    for (const ev of toolEvents) {
      if (ev.ok === false) continue;
      if (ev.name === "write_file" || ev.name === "str_replace") {
        const rawPath = ev.arguments?.path;
        if (rawPath) {
          const norm = normalizeRelativePath(rawPath);
          if (norm) pathsToReload.add(norm);
        }
      }
    }
    if (!pathsToReload.size) return;

    for (const relPath of pathsToReload) {
      const tab = findEditorTab(relPath);
      if (tab) {
        await openEditorFile(tab.path, { reload: true, keepActive: true });
      }
    }
  }

  function extFromMime(mime) {
    const normalized = String(mime || "")
      .toLowerCase()
      .split(";")[0]
      .trim();
    return MIME_TO_IMAGE_EXT[normalized] || "";
  }

  function ensureImageFilename(name, mime) {
    const base = String(name || "")
      .split(/[/\\]/)
      .pop()
      .trim();
    const ext = fileExt(base);
    if (IMAGE_EXTS.has(ext)) return base;
    const fromMime = extFromMime(mime);
    const stem =
      base && base !== "blob" && base !== "image"
        ? base.replace(/\.[^.]+$/, "")
        : "pasted-image";
    return `${stem}${fromMime || ".png"}`;
  }

  function clipboardImageFiles(dataTransfer) {
    const files = [];
    const seen = new Set();
    const add = (file) => {
      if (!file || !file.type.startsWith("image/")) return;
      const key = `${file.name}:${file.size}:${file.type}:${file.lastModified}`;
      if (seen.has(key)) return;
      seen.add(key);
      files.push(file);
    };
    if (dataTransfer.items) {
      for (const item of dataTransfer.items) {
        if (item.kind !== "file" || !item.type.startsWith("image/")) continue;
        add(item.getAsFile());
      }
    }
    if (!files.length && dataTransfer.files?.length) {
      for (const file of dataTransfer.files) add(file);
    }
    return files;
  }

  function readFileAsText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("Failed to read file"));
      reader.readAsText(file);
    });
  }

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        const comma = result.indexOf(",");
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      };
      reader.onerror = () => reject(reader.error || new Error("Failed to read image"));
      reader.readAsDataURL(file);
    });
  }

  function imagePreviewUrl(att) {
    if (att.preview_url) return att.preview_url;
    if (att.data_base64) {
      const mime = att.mime && att.mime.startsWith("image/") ? att.mime : "image/png";
      return `data:${mime};base64,${att.data_base64}`;
    }
    return "";
  }

  function renderAttachments() {
    const chips = els.attachChips;
    chips.innerHTML = "";
    const hasAttachments = state.attachments.length > 0;
    const hasSkill = Boolean(state.selectedSkill);
    if (!hasAttachments && !hasSkill) {
      chips.classList.add("hidden");
      return;
    }
    chips.classList.remove("hidden");

    if (hasSkill) {
      const chip = document.createElement("div");
      chip.className = "skill-chip";
      chip.title = state.selectedSkill.description || state.selectedSkill.name;
      const label = document.createElement("span");
      label.className = "skill-chip-label";
      label.textContent = "Skill:";
      const name = document.createElement("span");
      name.className = "truncate";
      name.textContent = state.selectedSkill.name;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className =
        "shrink-0 rounded px-1 text-teal-700/70 transition hover:bg-teal-100 hover:text-teal-900";
      remove.setAttribute("aria-label", `Remove skill ${state.selectedSkill.name}`);
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        clearSelectedSkill();
      });
      chip.append(label, name, remove);
      chips.appendChild(chip);
    }

    state.attachments.forEach((att, index) => {
      const chip = document.createElement("div");
      chip.className = "group relative shrink-0";

      if (att.kind === "image") {
        chip.className +=
          " h-16 w-16 overflow-hidden rounded-lg border border-slate-200 bg-slate-50";
        const img = document.createElement("img");
        img.src = imagePreviewUrl(att);
        img.alt = att.name || "Attached image";
        img.className = "h-full w-full object-cover";
        chip.appendChild(img);
      } else {
        chip.className +=
          " inline-flex max-w-full items-center gap-1.5 rounded-lg border border-slate-200 bg-page px-2 py-1 text-xs text-slate-700";
        const label = document.createElement("span");
        label.className = "truncate";
        label.textContent = `File: ${att.name}`;
        chip.appendChild(label);
      }

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className =
        att.kind === "image"
          ? "absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 bg-white text-xs leading-none text-slate-500 shadow-sm transition hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700"
          : "shrink-0 rounded px-1 text-slate-400 transition hover:bg-slate-200 hover:text-slate-700";
      remove.setAttribute("aria-label", `Remove ${att.name}`);
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        state.attachments.splice(index, 1);
        renderAttachments();
      });
      chip.appendChild(remove);
      chips.appendChild(chip);
    });

    if (state.supportsVision === false && state.attachments.some((a) => a.kind === "image")) {
      const hint = document.createElement("div");
      hint.className =
        "inline-flex items-center rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs text-amber-800";
      hint.textContent = "Model does not support vision; images will be attached as text references.";
      chips.appendChild(hint);
    }
  }

  function clearAttachments() {
    state.attachments = [];
    renderAttachments();
  }

  function clearSelectedSkill() {
    state.selectedSkill = null;
    if (els.btnSkills) els.btnSkills.classList.remove("is-active");
    renderAttachments();
  }

  function setSkillsMenuOpen(open) {
    state.skillsMenuOpen = open;
    if (!els.skillsMenu || !els.btnSkills) return;
    els.skillsMenu.classList.toggle("hidden", !open);
    els.btnSkills.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      requestAnimationFrame(() => positionSkillsMenu());
    }
  }

  function positionSkillsMenu() {
    if (!els.skillsMenu || !els.btnSkills || !state.skillsMenuOpen) return;

    const menu = els.skillsMenu;
    const anchor = els.btnSkills.getBoundingClientRect();
    const gap = 6;
    const margin = 8;
    const minWidth = 256;

    menu.style.visibility = "hidden";
    menu.style.left = "0";
    menu.style.top = "0";
    menu.style.minWidth = `${Math.max(anchor.width, minWidth)}px`;
    const menuHeight = menu.offsetHeight;
    const menuWidth = menu.offsetWidth;

    let left = anchor.left;
    left = Math.max(margin, Math.min(left, window.innerWidth - menuWidth - margin));

    const spaceAbove = anchor.top - gap;
    const spaceBelow = window.innerHeight - anchor.bottom - gap;
    let top;
    if (menuHeight + margin <= spaceAbove || spaceAbove >= spaceBelow) {
      top = anchor.top - menuHeight - gap;
    } else {
      top = anchor.bottom + gap;
    }
    top = Math.max(margin, Math.min(top, window.innerHeight - menuHeight - margin));

    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.style.visibility = "";
  }

  function renderSkillsMenu() {
    if (!els.skillsMenu) return;
    els.skillsMenu.innerHTML = "";
    const skills = state.skills || [];
    if (!skills.length) {
      const empty = document.createElement("div");
      empty.className = "skills-menu-empty";
      empty.textContent = "No skills installed yet.";
      els.skillsMenu.appendChild(empty);
      return;
    }
    for (const skill of skills) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "skills-menu-item";
      btn.setAttribute("role", "menuitem");
      btn.innerHTML = `
        <div class="skills-menu-item-name">${escapeHtml(skill.name)}</div>
        <div class="skills-menu-item-desc">${escapeHtml(skill.description || "")}</div>
      `;
      btn.addEventListener("click", () => {
        state.selectedSkill = {
          name: skill.name,
          description: skill.description || "",
        };
        if (els.btnSkills) els.btnSkills.classList.add("is-active");
        renderAttachments();
        setSkillsMenuOpen(false);
        showComposerStatus(`Skill selected: ${skill.name}`, "success");
        els.composer?.focus();
      });
      els.skillsMenu.appendChild(btn);
    }
  }

  function selectSkillFromCatalog(skills) {
    state.skills = skills || [];
    renderSkillsMenu();
    if (els.btnSkills) {
      els.btnSkills.disabled = state.busy;
      els.btnSkills.title = state.skills.length
        ? "Use an Agent Skill"
        : "No Agent Skills installed";
    }
  }

  async function addImageFile(file, { nameOverride } = {}) {
    if (state.attachments.length >= MAX_ATTACHMENTS) {
      showComposerStatus(`At most ${MAX_ATTACHMENTS} attachments per message.`, "warning");
      return false;
    }
    const name = ensureImageFilename(nameOverride || file.name, file.type);
    const ext = fileExt(name);
    if (!IMAGE_EXTS.has(ext)) {
      showComposerStatus(`Blocked image type: ${name}`, "warning");
      return false;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      showComposerStatus(`Image too large (max 20 MB): ${name}`, "warning");
      return false;
    }
    try {
      const data_base64 = await readFileAsBase64(file);
      const mime = file.type || "application/octet-stream";
      state.attachments.push({
        kind: "image",
        name,
        mime,
        data_base64,
        preview_url: `data:${mime.startsWith("image/") ? mime : "image/png"};base64,${data_base64}`,
      });
      showComposerStatus(`Attached ${name}`, "success");
      return true;
    } catch (err) {
      showComposerStatus(`Could not read ${name}: ${err.message || err}`, "error");
      return false;
    }
  }

  async function addFiles(fileList, kind) {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    for (const file of files) {
      if (state.attachments.length >= MAX_ATTACHMENTS) {
        showComposerStatus(`At most ${MAX_ATTACHMENTS} attachments per message.`, "warning");
        break;
      }
      if (kind === "image") {
        await addImageFile(file);
      } else {
        const ext = fileExt(file.name);
        if (!FILE_EXTS.has(ext)) {
          showComposerStatus(`Blocked file type: ${file.name}`, "warning");
          continue;
        }
        if (file.size > MAX_TEXT_BYTES) {
          showComposerStatus(`File too large (max 512 KB): ${file.name}`, "warning");
          continue;
        }
        try {
          const text = await readFileAsText(file);
          state.attachments.push({
            kind: "file",
            name: file.name,
            mime: file.type || "text/plain",
            text,
          });
          showComposerStatus(`Attached ${file.name}`, "success");
        } catch (err) {
          showComposerStatus(`Could not read ${file.name}: ${err.message || err}`, "error");
        }
      }
    }
    renderAttachments();
  }

  async function addExplorerFile(relativePath) {
    const rel = String(relativePath || "").replace(/\\/g, "/").trim();
    if (!rel) return;
    const name = rel.split("/").pop() || rel;
    const ext = fileExt(name);
    const isImage = IMAGE_EXTS.has(ext);
    const isText = FILE_EXTS.has(ext);
    if (!isImage && !isText) {
      showComposerStatus(`Blocked file type: ${name}`, "warning");
      return;
    }
    if (state.attachments.length >= MAX_ATTACHMENTS) {
      showComposerStatus(`At most ${MAX_ATTACHMENTS} attachments per message.`, "warning");
      return;
    }

    const res = await fetchProjectFile(rel);
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        /* ignore */
      }
      if (res.status === 404) {
        throw new Error(`File not found in project: ${rel}`);
      }
      throw new Error(detail);
    }
    const blob = await res.blob();
    const mime =
      blob.type ||
      (isImage ? "application/octet-stream" : "text/plain");
    const file = new File([blob], name, { type: mime });
    if (isImage) {
      const added = await addImageFile(file);
      if (added) renderAttachments();
    } else {
      if (file.size > MAX_TEXT_BYTES) {
        showComposerStatus(`File too large (max 512 KB): ${name}`, "warning");
        return;
      }
      const text = await readFileAsText(file);
      state.attachments.push({
        kind: "file",
        name,
        mime,
        text,
      });
      showComposerStatus(`Attached ${name}`, "success");
      renderAttachments();
    }
  }

  async function addDroppedFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    hideComposerStatus();

    for (const file of files) {
      if (state.attachments.length >= MAX_ATTACHMENTS) {
        showComposerStatus(`At most ${MAX_ATTACHMENTS} attachments per message.`, "warning");
        break;
      }
      const ext = fileExt(file.name);
      const kind =
        IMAGE_EXTS.has(ext) || String(file.type || "").startsWith("image/")
          ? "image"
          : "file";
      await addFiles([file], kind);
    }
  }

  function setComposerDragOver(active) {
    if (!els.composerWrap) return;
    els.composerWrap.classList.toggle("composer-drag-over", active);
  }

  function handleComposerDragEnter(e) {
    if (state.busy) return;
    e.preventDefault();
    setComposerDragOver(true);
  }

  function handleComposerDragOver(e) {
    if (state.busy) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setComposerDragOver(true);
  }

  function handleComposerDragLeave(e) {
    if (state.busy) return;
    const wrap = els.composerWrap;
    if (!wrap) return;
    if (e.relatedTarget instanceof Node && wrap.contains(e.relatedTarget)) return;
    setComposerDragOver(false);
  }

  async function handleComposerDrop(e) {
    e.preventDefault();
    setComposerDragOver(false);
    if (state.busy) return;

    hideComposerStatus();
    const dataTransfer = e.dataTransfer;
    const explorerDrag = isExplorerDrag(dataTransfer);
    const files = dataTransfer.files;

    try {
      if (explorerDrag) {
        const explorerPath = resolveExplorerDropPath(dataTransfer);
        if (explorerPath) {
          await addExplorerFile(explorerPath);
          return;
        }
      }

      if (files?.length) {
        await addDroppedFiles(files);
      }
    } catch (err) {
      showComposerStatus(err.message || String(err), "error");
    } finally {
      state.explorerDragPath = null;
    }
  }

  async function handleComposerPaste(e) {
    if (state.busy) return;
    const images = clipboardImageFiles(e.clipboardData);
    if (!images.length) return;

    e.preventDefault();
    hideComposerStatus();

    let added = 0;
    for (const file of images) {
      const suffix = images.length > 1 ? `-${added + 1}` : "";
      const defaultName = `pasted-image${suffix}${extFromMime(file.type) || ".png"}`;
      if (await addImageFile(file, { nameOverride: defaultName })) added += 1;
    }
    if (added) renderAttachments();
  }

  function optimisticUserText(text) {
    return (text || "").trim();
  }

  function optimisticUserMessage(message, attachments, skill) {
    const imageAttachments = attachments
      .filter((att) => att.kind === "image")
      .map((att) => ({
        kind: "image",
        name: att.name,
        mime: att.mime,
        preview_url: `data:${att.mime || "image/png"};base64,${att.data_base64}`,
      }));
    const fileAttachments = attachments
      .filter((att) => att.kind === "file")
      .map((att) => ({
        kind: "file",
        name: att.name,
        mime: att.mime,
      }));
    const entry = {
      role: "user",
      content: optimisticUserText(message),
      attachments: [...imageAttachments, ...fileAttachments],
    };
    if (skill) entry.skill = skill;
    return entry;
  }

  function currentTitle() {
    const s = state.sessions.find((x) => x.id === state.currentId);
    return s?.title || "New chat";
  }

  const COPY_ICON_SVG = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" class="h-3.5 w-3.5" aria-hidden="true">
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke-linejoin="round" />
    </svg>
  `;

  function formatElapsed(ms) {
    if (!Number.isFinite(ms) || ms < 0) return "";
    if (ms < 1000) return `${Math.round(ms)}ms`;
    const seconds = ms / 1000;
    if (seconds < 60) return `${seconds.toFixed(1).replace(/\.0$/, "")}s`;
    const mins = Math.floor(seconds / 60);
    const rem = Math.round(seconds % 60);
    return rem ? `${mins}m ${rem}s` : `${mins}m`;
  }

  function messageCopyText(msg) {
    if (!msg) return "";
    const content = (msg.content || "").trim();
    if (content) return content;
    if (msg.role === "user" && msg.skill) return `Skill: ${msg.skill}`;
    return "";
  }

  function messageIsTyping(msg, index) {
    if (msg.role !== "assistant") return false;
    const isLast = index === state.messages.length - 1;
    if (!isLast || !state.busy) return false;
    const segments = msg.segments || [];
    if (segments.some((seg) => seg.type === "status" && seg.active)) return false;
    const hasSegmentText = segments.some(
      (seg) => seg.type === "text" && (seg.content || "").trim()
    );
    const empty =
      !hasSegmentText &&
      !(msg.content || "").trim() &&
      !(msg.tool_events || []).length &&
      !(msg.activity || []).length &&
      !segments.length;
    return empty;
  }

  async function copyMessageText(text, btn) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    if (!btn) return;
    btn.classList.add("msg-copy-btn--copied");
    const prev = btn.title;
    btn.title = "Copied!";
    window.setTimeout(() => {
      btn.classList.remove("msg-copy-btn--copied");
      btn.title = prev || "Copy message";
    }, 1500);
  }

  function updateMessageFooter(wrap, msg, index) {
    const actions = wrap.querySelector(".msg-actions");
    if (!actions) return;

    const timeEl = actions.querySelector("[data-request-time]");
    const copyBtn = actions.querySelector("[data-copy-btn]");
    const isUser = msg.role === "user";
    const typing = messageIsTyping(msg, index);
    const copyText = messageCopyText(msg);
    const canCopy = Boolean(copyText) && !typing;

    if (timeEl) {
      const elapsed = !isUser && Number.isFinite(msg.elapsed_ms) ? msg.elapsed_ms : null;
      if (elapsed != null && elapsed >= 0) {
        timeEl.textContent = formatElapsed(elapsed);
        timeEl.classList.remove("hidden");
      } else {
        timeEl.textContent = "";
        timeEl.classList.add("hidden");
      }
    }

    if (copyBtn) {
      copyBtn.classList.toggle("hidden", !canCopy);
      copyBtn.disabled = !canCopy;
      copyBtn.dataset.copyText = canCopy ? copyText : "";
    }
  }

  function formatRelativeTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const diffMs = Date.now() - d.getTime();
    if (diffMs < 0) return "Just now";
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "Just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 7) return `${days}d ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function createSessionButton(session) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.id = session.id;
    const active = session.id === state.currentId;
    btn.className = active
      ? "mb-1 w-full truncate rounded-lg bg-accent-soft px-3 py-2 text-left text-sm font-medium text-accent transition"
      : "mb-1 w-full truncate rounded-lg px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-50";
    btn.textContent = session.title || "Untitled";
    btn.addEventListener("click", () => selectSession(session.id));
    return btn;
  }

  function createRecentSessionButton(session) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.id = session.id;
    const active = session.id === state.currentId;
    const when = formatRelativeTime(session.created);
    const status = active ? "Viewing now" : "Resume chat";
    const meta = [when, status].filter(Boolean).join(" · ");

    btn.className = active
      ? "group w-full rounded-lg border border-accent bg-accent-soft px-3 py-2.5 text-left shadow-sm ring-1 ring-accent/15 transition hover:bg-teal-100/60"
      : "group w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-left shadow-sm transition hover:border-slate-300 hover:bg-slate-50";

    btn.innerHTML = `
      <div class="text-[10px] font-medium uppercase tracking-wider text-slate-400">Latest chat</div>
      <div class="mt-1.5 flex items-start gap-2.5">
        <span class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${
          active ? "bg-accent/15 text-accent" : "bg-slate-100 text-slate-500 group-hover:bg-slate-200"
        }" aria-hidden="true">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" class="h-4 w-4">
            <path d="M8 10h8M8 14h5" stroke-linecap="round" />
            <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3h9A2.5 2.5 0 0 1 19 5.5v9A2.5 2.5 0 0 1 16.5 17H9l-4 4v-4.5" stroke-linejoin="round" />
          </svg>
        </span>
        <span class="min-w-0 flex-1">
          <span class="block truncate text-sm font-medium leading-snug ${
            active ? "text-accent" : "text-ink"
          }">${escapeHtml(session.title || "Untitled")}</span>
          <span class="mt-0.5 block truncate text-[11px] leading-snug ${
            active ? "text-accent/80" : "text-slate-500"
          }">${escapeHtml(meta)}</span>
        </span>
      </div>
    `;
    btn.addEventListener("click", () => selectSession(session.id));
    return btn;
  }

  function renderSessions() {
    els.sessionList.innerHTML = "";
    if (els.sessionRecent) els.sessionRecent.innerHTML = "";

    const count = state.sessions.length;
    const olderCount = Math.max(0, count - 1);

    if (els.chatsCount) {
      els.chatsCount.textContent =
        count === 0
          ? "No saved chats"
          : count === 1
            ? "1 chat"
            : `${count} chats`;
    }

    if (els.chatsToggle) {
      els.chatsToggle.classList.toggle("hidden", olderCount === 0);
      els.chatsToggle.classList.toggle("flex", olderCount > 0);
    }
    if (els.chatsToggleLabel) {
      els.chatsToggleLabel.textContent =
        olderCount === 1 ? "1 older chat" : `${olderCount} older chats`;
    }
    if (olderCount === 0 && state.chatsExpanded) {
      setChatsExpanded(false);
    }

    if (!count) {
      if (els.sessionRecent) {
        els.sessionRecent.innerHTML =
          '<p class="px-2 py-1 text-xs text-slate-400">No saved chats yet.</p>';
      }
      if (olderCount === 0) setChatsExpanded(false);
      return;
    }

    const [recent, ...older] = state.sessions;
    if (els.sessionRecent) {
      els.sessionRecent.appendChild(createRecentSessionButton(recent));
    }
    for (const session of older) {
      els.sessionList.appendChild(createSessionButton(session));
    }
  }

  function attachmentUrl(attachmentId) {
    if (!state.currentId || !attachmentId) return "";
    return `/api/sessions/${encodeURIComponent(state.currentId)}/attachments/${encodeURIComponent(attachmentId)}`;
  }

  function renderUserAttachments(container, attachments) {
    if (!attachments.length) return;

    const wrap = document.createElement("div");
    wrap.className = "mb-3 flex flex-wrap gap-2";

    for (const att of attachments) {
      if (att.kind === "image") {
        const item = document.createElement("div");
        item.className =
          "overflow-hidden rounded-lg border border-slate-200 bg-slate-50";
        const img = document.createElement("img");
        img.src = att.preview_url || attachmentUrl(att.id);
        img.alt = att.name || "Attached image";
        img.loading = "lazy";
        img.className = "max-h-48 max-w-full object-contain";
        item.appendChild(img);
        wrap.appendChild(item);
        continue;
      }

      if (att.kind === "file") {
        const chip = document.createElement("div");
        chip.className =
          "inline-flex max-w-full items-center gap-2 rounded-lg border border-slate-200 bg-page px-2.5 py-1.5 text-xs text-slate-700";
        chip.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" class="h-4 w-4 shrink-0 text-slate-400" aria-hidden="true">
            <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" stroke-linejoin="round" />
            <path d="M14 3v5h5" stroke-linejoin="round" />
          </svg>
          <span class="truncate font-medium">${escapeHtml(att.name || "File")}</span>
        `;
        wrap.appendChild(chip);
      }
    }

    container.appendChild(wrap);
  }

  function toolEventSummary(ev) {
    const args = ev.arguments || {};
    const name = ev.name || "tool";
    const path = args.path || args.url || args.expression || args.attachment_id;
    if (path) return `${name} → ${path}`;
    if (args.command) {
      const cmd = String(args.command);
      return `${name} → ${cmd.length > 72 ? cmd.slice(0, 72) + "…" : cmd}`;
    }
    if (args.pattern) return `${name} → /${args.pattern}/`;
    return name;
  }

  function renderToolEventDetails(ev) {
    const ok = ev.ok !== false;
    const details = document.createElement("details");
    details.className = "tool-event rounded-lg border px-2.5 py-2";
    details.dataset.ok = ok ? "true" : "false";
    if (!ok) details.open = true;

    const summary = document.createElement("summary");
    summary.className = "flex items-start gap-2 text-[11px] leading-snug";
    summary.innerHTML = `
      <span class="mt-0.5 shrink-0 font-semibold ${ok ? "text-teal-700" : "text-red-700"}">${ok ? "✓" : "✗"}</span>
      <span class="min-w-0 flex-1 font-mono text-slate-700">${escapeHtml(toolEventSummary(ev))}</span>
    `;
    details.appendChild(summary);

    const body = document.createElement("div");
    body.className = "tool-event-body";
    const argText = JSON.stringify(ev.arguments || {}, null, 2);
    body.textContent = `${argText}\n\n→ ${ev.result || ""}`;
    details.appendChild(body);
    return details;
  }

  function renderToolEvents(container, events) {
    const existing = container.querySelector(".tool-events");
    if (existing) existing.remove();
    if (!events?.length) return;

    const wrap = document.createElement("div");
    wrap.className = "tool-events mb-3";
    for (const ev of events) {
      wrap.appendChild(renderToolEventDetails(ev));
    }
    container.insertBefore(wrap, container.firstChild);
  }

  function appendActivityElapsed(parent, item) {
    const ms = activityElapsedMs(item);
    const elapsed = document.createElement("div");
    elapsed.className = "activity-elapsed";
    if (Number.isFinite(ms) && ms >= 0) {
      elapsed.dataset.elapsedMs = String(ms);
      elapsed.textContent = formatElapsed(ms);
    }
    parent.appendChild(elapsed);
  }

  function appendActivityLabelText(labelEl, item) {
    if (item.kind === "thinking") {
      const wrap = document.createElement("div");
      wrap.className = "min-w-0 flex-1";

      const title = document.createElement("div");
      title.className = "activity-thinking-title";
      title.textContent = item.active
        ? "Thinking…"
        : item.snippet || item.label || "Thought briefly";
      wrap.appendChild(title);

      if (item.active && item.snippet) {
        const snippet = document.createElement("div");
        snippet.className = "activity-thinking-snippet";
        snippet.textContent = item.snippet;
        wrap.appendChild(snippet);
      }

      labelEl.appendChild(wrap);
      return;
    }

    const text = document.createElement("span");
    text.className = "min-w-0 flex-1";
    text.textContent = item.label || item.kind || "Working…";
    labelEl.appendChild(text);
  }

  function renderStatusSegment(item) {
    if (item.kind === "responding") return null;

    const row = document.createElement("div");
    row.className = "activity-item";
    row.dataset.segmentId = item.id || "";
    row.dataset.kind = item.kind || "status";
    row.dataset.active = item.active ? "true" : "false";
    if (item.kind === "tool_done") row.dataset.ok = item.ok === false ? "false" : "true";

    if (item.kind === "tool_done") {
      const details = renderToolEventDetails({
        name: item.name,
        arguments: item.arguments || {},
        result: item.result || "",
        ok: item.ok !== false,
      });
      const summary = details.querySelector("summary");
      if (summary) {
        summary.innerHTML = `
          <span class="min-w-0 flex-1 font-mono text-slate-700">${escapeHtml(item.label || toolEventSummary(item))}</span>
        `;
      }
      row.appendChild(details);
      appendActivityElapsed(row, item);
      return row;
    }

    const label = document.createElement("div");
    label.className = "activity-label";

    const icon = document.createElement("span");
    icon.className = "activity-icon";
    if (item.active) {
      icon.classList.add("activity-icon--pulse");
      icon.setAttribute("aria-hidden", "true");
    } else if (item.kind === "thinking") {
      icon.textContent = "◦";
      icon.className += " text-teal-600";
    } else {
      icon.textContent = "›";
      icon.className += " text-slate-400";
    }
    label.appendChild(icon);

    appendActivityLabelText(label, item);
    row.appendChild(label);
    appendActivityElapsed(row, item);
    return row;
  }

  function renderTextSegment(item) {
    const content = item.content || "";
    if (!content.trim()) return null;

    const block = document.createElement("div");
    block.className = "activity-content-block";
    block.dataset.segmentId = item.id || "";

    const prose = document.createElement("div");
    prose.innerHTML = renderMarkdown(item.content || "");
    block.appendChild(prose);

    appendActivityElapsed(block, item);
    return block;
  }

  function renderTurnTimeline(container, msg) {
    const existing = container.querySelector(".activity-timeline");
    if (existing) existing.remove();
    container.querySelectorAll(".activity-content-block").forEach((el) => el.remove());

    const segments = msg.segments || [];
    if (!segments.length) {
      renderActivityTimeline(container, msg);
      const content = (msg.content || "").trim();
      if (content) {
        const block = document.createElement("div");
        block.className = "activity-content-block";
        const prose = document.createElement("div");
        prose.innerHTML = renderMarkdown(content);
        block.appendChild(prose);
        const elapsed = document.createElement("div");
        elapsed.className = "activity-elapsed activity-content-elapsed";
        if (Number.isFinite(msg.elapsed_ms) && msg.elapsed_ms >= 0) {
          elapsed.dataset.elapsedMs = String(msg.elapsed_ms);
          elapsed.textContent = formatElapsed(msg.elapsed_ms);
        }
        block.appendChild(elapsed);
        container.appendChild(block);
      }
      return;
    }

    const wrap = document.createElement("div");
    wrap.className = "activity-timeline";

    for (const seg of segments) {
      if (seg.type === "text") {
        const node = renderTextSegment(seg);
        if (node) wrap.appendChild(node);
        continue;
      }
      if (seg.type === "status") {
        const node = renderStatusSegment(seg);
        if (node) wrap.appendChild(node);
      }
    }

    container.appendChild(wrap);
  }

  function renderActivityTimeline(container, msg) {
    const existing = container.querySelector(".activity-timeline");
    if (existing) existing.remove();

    const activity = msg.activity || [];
    if (!activity.length) {
      if ((msg.tool_events || []).length) {
        renderToolEvents(container, msg.tool_events);
      }
      return null;
    }

    const wrap = document.createElement("div");
    wrap.className = "activity-timeline";

    for (const item of activity) {
      const row = document.createElement("div");
      row.className = "activity-item";
      row.dataset.kind = item.kind || "status";
      row.dataset.active = item.active ? "true" : "false";
      if (item.kind === "tool_done") row.dataset.ok = item.ok === false ? "false" : "true";

      if (item.kind === "tool_done") {
        const details = renderToolEventDetails({
          name: item.name,
          arguments: item.arguments || {},
          result: item.result || "",
          ok: item.ok !== false,
        });
        const summary = details.querySelector("summary");
        if (summary) {
          summary.innerHTML = `
            <span class="min-w-0 flex-1 font-mono text-slate-700">${escapeHtml(item.label || toolEventSummary(item))}</span>
          `;
        }
        row.appendChild(details);
        appendActivityElapsed(row, item);
        wrap.appendChild(row);
        continue;
      }

      const label = document.createElement("div");
      label.className = "activity-label";

      const icon = document.createElement("span");
      icon.className = "activity-icon";
      if (item.active) {
        icon.classList.add("activity-icon--pulse");
        icon.setAttribute("aria-hidden", "true");
      } else if (item.kind === "thinking") {
        icon.textContent = "◦";
        icon.className += " text-teal-600";
      } else {
        icon.textContent = "›";
        icon.className += " text-slate-400";
      }
      label.appendChild(icon);

      appendActivityLabelText(label, item);
      row.appendChild(label);
      appendActivityElapsed(row, item);
      wrap.appendChild(row);
    }

    container.appendChild(wrap);

    const responding = [...activity].reverse().find((item) => item.kind === "responding");
    return responding ? activityElapsedMs(responding) : null;
  }

  function fillMessageBody(body, msg, index = -1) {
    const isUser = msg.role === "user";
    const content = msg.content || "";
    const typing = !isUser && messageIsTyping(msg, index);
    const attKey = msg.attachments ? JSON.stringify(msg.attachments) : "";
    const skillKey = msg.skill || "";
    const toolKey = msg.tool_events ? JSON.stringify(msg.tool_events) : "";
    const activityKey = msg.activity ? JSON.stringify(msg.activity) : "";
    const segmentsKey = msg.segments ? JSON.stringify(msg.segments) : "";
    const busyKey = !isUser && state.busy ? "1" : "0";
    const key = `${msg.role}:${typing ? "__typing__" : content}:${attKey}:${skillKey}:${toolKey}:${activityKey}:${segmentsKey}:${busyKey}`;
    if (body.dataset.contentKey === key) return;
    body.dataset.contentKey = key;

    if (isUser) {
      body.classList.add("whitespace-pre-wrap");
      body.classList.remove("msg-prose");
      body.innerHTML = "";

      if (msg.skill) {
        const skillChip = document.createElement("div");
        skillChip.className = "msg-skill-chip";
        skillChip.textContent = `Skill: ${msg.skill}`;
        body.appendChild(skillChip);
      }

      const attachments = msg.attachments || [];
      if (attachments.length) {
        renderUserAttachments(body, attachments);
      }

      if (content.trim()) {
        const text = document.createElement("div");
        text.textContent = content;
        body.appendChild(text);
      }
      return;
    }

    body.classList.remove("whitespace-pre-wrap");
    body.classList.add("msg-prose");
    body.innerHTML = "";

    renderTurnTimeline(body, msg);

    if (typing) {
      const dots = document.createElement("div");
      dots.className = "typing-dots";
      dots.setAttribute("aria-label", "Agent is starting");
      dots.setAttribute("role", "status");
      dots.innerHTML = "<span></span><span></span><span></span>";
      body.appendChild(dots);
    }
  }

  function buildMessageEl(msg, { animate = false, index = -1 } = {}) {
    const wrap = document.createElement("div");
    wrap.dataset.role = msg.role;
    if (animate) wrap.className = "animate-fadeIn";
    const isUser = msg.role === "user";
    wrap.innerHTML = `
      <div class="mb-1 text-[11px] font-medium uppercase tracking-wider ${
        isUser ? "text-slate-400" : "text-accent"
      }">${isUser ? "You" : "Agent"}</div>
      <div data-msg-body class="rounded-2xl border px-4 py-3 text-sm leading-relaxed ${
        isUser
          ? "border-slate-200 bg-white text-ink"
          : "border-teal-100 bg-white text-ink msg-prose"
      }"></div>
      <div class="msg-actions mt-1.5 flex items-center gap-2">
        <span data-request-time class="hidden text-[11px] text-slate-400"></span>
        <button
          type="button"
          data-copy-btn
          class="msg-copy-btn hidden"
          title="Copy message"
          aria-label="Copy message"
        >${COPY_ICON_SVG}</button>
      </div>
    `;
    fillMessageBody(wrap.querySelector("[data-msg-body]"), msg, index);
    updateMessageFooter(wrap, msg, index);
    return wrap;
  }

  function nearBottom(threshold = 32) {
    const el = els.messages;
    return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  }

  function scrollMessagesToBottom() {
    els.messages.scrollTop = els.messages.scrollHeight;
  }

  function renderMessages({ animate = false } = {}) {
    const has = state.messages.length > 0;
    els.emptyState.classList.toggle("hidden", has);
    els.messageList.classList.toggle("hidden", !has);
    els.messageList.innerHTML = "";
    els.chatTitle.textContent = currentTitle();

    for (let i = 0; i < state.messages.length; i++) {
      els.messageList.appendChild(buildMessageEl(state.messages[i], { animate, index: i }));
    }
    state.autoScrollMessages = true;
    scrollMessagesToBottom();
  }

  /** Update chat DOM without wiping it on every stream token. */
  function syncMessages({ animateNew = false } = {}) {
    const has = state.messages.length > 0;
    els.emptyState.classList.toggle("hidden", has);
    els.messageList.classList.toggle("hidden", !has);
    els.chatTitle.textContent = currentTitle();

    const children = Array.from(els.messageList.children);
    const msgs = state.messages;
    const sameStructure =
      children.length === msgs.length &&
      children.every((el, i) => el.dataset.role === msgs[i].role);

    const stick = state.autoScrollMessages;

    if (!sameStructure) {
      // Append-only growth (typical send / stream start): keep existing nodes.
      if (
        children.length < msgs.length &&
        children.every((el, i) => el.dataset.role === msgs[i].role)
      ) {
        for (let i = 0; i < children.length; i++) {
          fillMessageBody(children[i].querySelector("[data-msg-body]"), msgs[i], i);
          updateMessageFooter(children[i], msgs[i], i);
        }
        for (let i = children.length; i < msgs.length; i++) {
          els.messageList.appendChild(
            buildMessageEl(msgs[i], { animate: animateNew, index: i })
          );
        }
      } else {
        els.messageList.innerHTML = "";
        for (let i = 0; i < msgs.length; i++) {
          els.messageList.appendChild(buildMessageEl(msgs[i], { animate: animateNew, index: i }));
        }
      }
    } else {
      for (let i = 0; i < msgs.length; i++) {
        fillMessageBody(children[i].querySelector("[data-msg-body]"), msgs[i], i);
        updateMessageFooter(children[i], msgs[i], i);
      }
    }

    if (stick) scrollMessagesToBottom();
  }

  function applySessionList(sessions) {
    state.sessions = sessions || [];
    renderSessions();
    els.chatTitle.textContent = currentTitle();
  }

  function compactTokens(n) {
    if (!Number.isFinite(n)) return "—";
    if (n >= 1000) {
      const k = n / 1000;
      return `${k >= 10 ? Math.round(k) : k.toFixed(1).replace(/\.0$/, "")}k`;
    }
    return String(n);
  }

  function formatVram(mib) {
    if (!Number.isFinite(mib)) return "—";
    if (mib >= 1024) {
      const gib = mib / 1024;
      return `${gib >= 10 ? Math.round(gib) : gib.toFixed(1).replace(/\.0$/, "")} GB`;
    }
    return `${Math.round(mib)} MB`;
  }

  function gpuBarColor(pct) {
    if (pct == null) return "#0D9488";
    if (pct >= 0.92) return "#E11D48";
    if (pct >= 0.75) return "#F59E0B";
    return "#0D9488";
  }

  function renderGpuMeter(gpu) {
    if (!els.gpuMeter) return;

    if (!gpu || !Number.isFinite(gpu.total_mib) || gpu.total_mib <= 0) {
      if (els.gpuName) els.gpuName.textContent = "No NVIDIA GPU detected";
      if (els.gpuCapacity) els.gpuCapacity.textContent = "Install drivers or use nvidia-smi";
      if (els.gpuBarWeights) els.gpuBarWeights.style.width = "0%";
      if (els.gpuBarContext) els.gpuBarContext.style.width = "0%";
      if (els.gpuBarOther) els.gpuBarOther.style.width = "0%";
      if (els.gpuVramLabel) els.gpuVramLabel.textContent = "VRAM unavailable";
      return;
    }

    const total = gpu.total_mib;
    const weights = Number.isFinite(gpu.weights_mib) ? gpu.weights_mib : 0;
    const context = Number.isFinite(gpu.context_mib) ? gpu.context_mib : 0;
    const other = Number.isFinite(gpu.other_vram_mib) ? gpu.other_vram_mib : 0;
    const used = weights + context + other;
    const fillPct = Math.min(used / total, 1);

    if (els.gpuName) els.gpuName.textContent = gpu.name || "—";
    if (els.gpuCapacity) {
      const ctx =
        gpu.model_loaded && Number.isFinite(gpu.context_length)
          ? ` · ${compactTokens(gpu.context_length)} ctx`
          : "";
      els.gpuCapacity.textContent = `${formatVram(total)} VRAM${ctx}`;
    }
    if (els.gpuBarWeights) {
      els.gpuBarWeights.style.width = `${Math.min((weights / total) * 100, 100)}%`;
    }
    if (els.gpuBarContext) {
      els.gpuBarContext.style.width = `${Math.min((context / total) * 100, 100)}%`;
      els.gpuBarContext.style.backgroundColor = gpuBarColor(fillPct);
    }
    if (els.gpuBarOther) {
      els.gpuBarOther.style.width = `${Math.min((other / total) * 100, 100)}%`;
    }

    const freeLabel = Number.isFinite(gpu.free_mib) ? formatVram(gpu.free_mib) : "—";
    if (els.gpuVramLabel) {
      if (gpu.model_loaded && weights > 0) {
        const parts = [`${formatVram(weights)} weights`];
        if (context > 0) parts.push(`${formatVram(context)} context`);
        parts.push(`${freeLabel} free`);
        els.gpuVramLabel.textContent = parts.join(" · ");
      } else if (other > 0) {
        els.gpuVramLabel.textContent = `${formatVram(other)} in use · ${freeLabel} free`;
      } else {
        els.gpuVramLabel.textContent = `${freeLabel} free`;
      }
    }
  }

  function ringColor(pct) {
    if (pct == null) return "#CBD5E1"; // unknown / no data yet
    if (pct >= 0.85) return "#E11D48"; // rose — nearly full
    if (pct >= 0.6) return "#F59E0B"; // amber — getting full
    return "#0D9488"; // teal — plenty of room
  }

  /** Paint both rings from the current ctx state. */
  function renderContextMeter() {
    const { used, window: win, max } = state.ctx;
    const hasWindow = Number.isFinite(win) && win > 0;
    const hasUsed = Number.isFinite(used);
    const pct = hasWindow && hasUsed ? Math.min(used / win, 1) : null;
    const offset = pct == null ? 100 : 100 - Math.max(pct, 0.0) * 100;
    const color = ringColor(pct);
    const pctLabel = pct == null ? "—" : `${Math.round(pct * 100)}%`;

    if (els.ctxRing) {
      els.ctxRing.style.strokeDashoffset = String(offset);
      els.ctxRing.style.stroke = color;
    }
    if (els.ctxPct) els.ctxPct.textContent = pctLabel;
    if (els.ctxTokens) {
      els.ctxTokens.textContent = `${hasUsed ? used.toLocaleString() : "—"} / ${
        hasWindow ? win.toLocaleString() : "—"
      }`;
    }
    if (els.ctxSub) {
      els.ctxSub.textContent =
        hasWindow && Number.isFinite(max) && max > win
          ? `tokens · model max ${compactTokens(max)}`
          : "tokens used";
    }

    if (els.ctxMini) {
      els.ctxMini.classList.toggle("sm:inline-flex", pct != null);
      els.ctxMini.classList.toggle("hidden", pct == null);
    }
    if (els.ctxMiniRing) {
      els.ctxMiniRing.style.strokeDashoffset = String(offset);
      els.ctxMiniRing.style.stroke = color;
    }
    if (els.ctxMiniText) els.ctxMiniText.textContent = pctLabel;
  }

  function setContextUsed(usage) {
    const total = usage && Number.isFinite(usage.total_tokens)
      ? usage.total_tokens
      : null;
    state.ctx.used = total;
    renderContextMeter();
  }

  function setToolsExpanded(expanded) {
    state.toolsExpanded = expanded;
    if (!els.toolsList || !els.toolsToggle) return;
    els.toolsList.classList.toggle("hidden", !expanded);
    els.toolsList.classList.toggle("flex", expanded);
    els.toolsToggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    if (els.toolsChevron) {
      els.toolsChevron.classList.toggle("rotate-180", expanded);
    }
  }

  function setChatsExpanded(expanded) {
    state.chatsExpanded = expanded;
    if (!els.chatsPanel || !els.chatsToggle) return;
    els.chatsPanel.classList.toggle("hidden", !expanded);
    els.chatsPanel.classList.toggle("flex", expanded);
    els.chatsToggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    if (els.chatsChevron) {
      els.chatsChevron.classList.toggle("rotate-180", expanded);
    }
  }

  function applyBasicStatus(data) {
    state.localProvider = data.local !== false;
    state.supportsVision = Boolean(data.supports_vision);
    if (els.statusProvider) {
      els.statusProvider.textContent = data.provider_label || data.provider || "—";
    }
    els.statusModel.textContent = data.model || "—";
    if (els.gpuMeter) {
      els.gpuMeter.classList.toggle("hidden", !state.localProvider);
    }
    els.statusCwd.textContent = data.cwd || "—";
    if (data.project) {
      applyProject(data.project);
    }
    const tools = data.tools || [];
    selectSkillFromCatalog(data.skills || []);
    const availableCount = tools.filter((t) => t.available !== false).length;
    if (els.toolsCount) {
      if (availableCount === tools.length) {
        els.toolsCount.textContent =
          tools.length === 1 ? "1 tool available" : `${tools.length} tools available`;
      } else {
        els.toolsCount.textContent = `${availableCount} of ${tools.length} tools available`;
      }
    }
    els.toolsList.innerHTML = "";
    for (const tool of tools) {
      const isAvailable = tool.available !== false;
      const chip = document.createElement("div");
      if (isAvailable) {
        chip.className = "rounded-lg border border-slate-200 bg-page px-2.5 py-2";
        chip.innerHTML = `
          <div class="font-mono text-xs font-medium text-ink">${escapeHtml(tool.name)}</div>
          <div class="mt-0.5 text-[11px] leading-snug text-slate-500">${escapeHtml(
            (tool.description || "").split(".")[0] + (tool.description ? "." : "")
          )}</div>
        `;
      } else {
        chip.className = "rounded-lg border border-slate-200 bg-page px-2.5 py-2 opacity-60";
        chip.innerHTML = `
          <div class="flex items-center justify-between gap-1">
            <span class="font-mono text-xs font-medium text-slate-600">${escapeHtml(tool.name)}</span>
            <span class="text-[10px] uppercase font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded px-1">Unavailable</span>
          </div>
          <div class="mt-0.5 text-[11px] leading-snug text-slate-400">${escapeHtml(
            (tool.description || "").split(".")[0] + (tool.description ? "." : "")
          )}</div>
          ${
            tool.unavailable_reason
              ? `<div class="mt-1 text-[10px] text-amber-800 leading-tight">${escapeHtml(
                  tool.unavailable_reason
                )}</div>`
              : ""
          }
        `;
      }
      els.toolsList.appendChild(chip);
    }
  }

  function applyContextCapacity(data) {
    state.ctx.window = Number.isFinite(data.context_length)
      ? data.context_length
      : null;
    state.ctx.max = Number.isFinite(data.max_context_length)
      ? data.max_context_length
      : null;
    renderContextMeter();
  }

  function applyGpuStatus(gpu) {
    renderGpuMeter(gpu);
  }

  async function loadBasicStatus() {
    setWidgetLoading(els.modelLoading, true);
    setWidgetLoading(els.cwdLoading, true);
    setWidgetLoading(els.toolsLoading, true);
    try {
      const data = await api("/api/status");
      applyBasicStatus(data);
    } finally {
      setWidgetLoading(els.modelLoading, false);
      setWidgetLoading(els.cwdLoading, false);
      setWidgetLoading(els.toolsLoading, false);
    }
  }

  async function loadRuntimeStatus({ gpu = true, context = true } = {}) {
    const fetchGpu = gpu && state.localProvider && !state.gpuLoaded;
    if (fetchGpu) setWidgetLoading(els.gpuLoading, true);
    if (context) setWidgetLoading(els.ctxLoading, true);
    try {
      const data = await api("/api/status/runtime");
      if (context) applyContextCapacity(data);
      if (fetchGpu) {
        applyGpuStatus(data.gpu);
        state.gpuLoaded = true;
      }
    } finally {
      if (fetchGpu) setWidgetLoading(els.gpuLoading, false);
      if (context) setWidgetLoading(els.ctxLoading, false);
    }
  }

  async function loadSessions() {
    setWidgetLoading(els.chatsLoading, true);
    try {
      const data = await api("/api/sessions");
      applySessionList(data.sessions);
    } catch (err) {
      const msg = `<p class="px-2 py-3 text-xs text-rose-500">Could not load chats: ${escapeHtml(err.message || String(err))}</p>`;
      if (els.sessionRecent) els.sessionRecent.innerHTML = msg;
      els.sessionList.innerHTML = "";
      throw err;
    } finally {
      setWidgetLoading(els.chatsLoading, false);
    }
  }

  async function selectSession(id) {
    if (state.busy) return;
    if (!id) {
      state.currentId = null;
      state.messages = [];
      setContextUsed(null);
      clearAttachments();
      renderSessions();
      renderMessages();
      els.logStatus.textContent = "";
      return;
    }
    const data = await api(`/api/sessions/${id}`);
    state.currentId = data.id;
    state.messages = data.messages || [];
    setContextUsed(data.usage);
    clearAttachments();
    renderSessions();
    renderMessages();
    els.logStatus.textContent = "";
  }

  async function newChat() {
    if (state.busy) return;
    state.currentId = null;
    state.messages = [];
    setContextUsed(null);
    clearAttachments();
    hideConfirms();
    renderSessions();
    renderMessages();
    els.logStatus.textContent = "";
    focusComposer();
  }

  function hideConfirms() {
    els.confirmDelete.classList.add("hidden");
    els.confirmClear.classList.add("hidden");
    state.pendingDeleteId = null;
  }

  function showDeleteConfirm() {
    if (!state.currentId) return;
    const s = state.sessions.find((x) => x.id === state.currentId);
    const title = s?.title || "this chat";
    state.pendingDeleteId = state.currentId;
    els.confirmDeleteText.textContent = `Delete chat “${title}”? This cannot be undone.`;
    els.confirmClear.classList.add("hidden");
    els.confirmDelete.classList.remove("hidden");
  }

  async function confirmDelete() {
    const id = state.pendingDeleteId;
    if (!id) return;
    const data = await api(`/api/sessions/${id}`, { method: "DELETE" });
    applySessionList(data.sessions);
    if (state.currentId === id) {
      state.currentId = null;
      state.messages = [];
      setContextUsed(null);
    }
    hideConfirms();
    renderMessages();
  }

  function showClearConfirm() {
    if (!state.sessions.length) return;
    els.confirmDelete.classList.add("hidden");
    els.confirmClear.classList.remove("hidden");
  }

  async function confirmClear() {
    const data = await api("/api/sessions", { method: "DELETE" });
    applySessionList(data.sessions);
    state.currentId = null;
    state.messages = [];
    setContextUsed(null);
    hideConfirms();
    renderMessages();
  }

  async function openLog() {
    const data = await api("/api/open-log", {
      method: "POST",
      body: JSON.stringify({ session_id: state.currentId }),
    });
    els.logStatus.textContent = data.message || "";
  }

  async function stopGeneration() {
    if (!state.busy) return;
    try {
      const data = await api("/api/stop", {
        method: "POST",
        body: JSON.stringify({
          session_id: state.currentId,
          messages: state.messages,
        }),
      });
      if (data.messages) {
        state.messages = data.messages;
        syncMessages();
      }
    } catch (err) {
      els.logStatus.textContent = `Stop failed: ${err.message || err}`;
      return;
    }
    if (state.chatAbortController) {
      state.chatAbortController.abort();
      state.chatAbortController = null;
    }
  }

  async function sendMessage(text) {
    const message = text.trim();
    const attachments = state.attachments.slice();
    const skill = state.selectedSkill?.name || null;
    if ((!message && !attachments.length && !skill) || state.busy) return;

    state.autoScrollMessages = true;
    setBusy(true);
    els.composer.value = "";
    clearAttachments();
    clearSelectedSkill();
    setSkillsMenuOpen(false);
    hideComposerStatus();
    autoResize();
    els.logStatus.textContent = "";

    const requestStartedAt = performance.now();
    state.requestStartedAt = requestStartedAt;
    const chatAbortController = new AbortController();
    state.chatAbortController = chatAbortController;

    // Optimistic user bubble; server will stream full history (with file bodies).
    state.messages = [
      ...state.messages,
      optimisticUserMessage(message, attachments, skill),
      { role: "assistant", content: "", tool_events: [], activity: [], segments: [] },
    ];
    syncMessages({ animateNew: true });

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: chatAbortController.signal,
        body: JSON.stringify({
          message,
          session_id: state.currentId,
          skill,
          attachments: attachments.map((att) =>
            att.kind === "image"
              ? {
                  kind: "image",
                  name: att.name,
                  mime: att.mime,
                  data_base64: att.data_base64,
                }
              : {
                  kind: "file",
                  name: att.name,
                  mime: att.mime,
                  text: att.text,
                }
          ),
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          const line = chunk
            .split("\n")
            .map((l) => l.trim())
            .find((l) => l.startsWith("data:"));
          if (!line) continue;
          const payload = JSON.parse(line.slice(5).trim());
          handleSse(payload);
        }
      }
    } catch (err) {
      const aborted =
        err?.name === "AbortError" ||
        /aborted|abort/i.test(String(err.message || ""));
      if (aborted) {
        return;
      }
      const last = state.messages[state.messages.length - 1];
      if (last && last.role === "assistant") {
        last.content =
          (last.content || "") + `\n\n**Error:** \`${err.message || err}\``;
      } else {
        state.messages.push({
          role: "assistant",
          content: `**Error:** \`${err.message || err}\``,
        });
      }
      syncMessages();
    } finally {
      if (state.chatAbortController === chatAbortController) {
        state.chatAbortController = null;
      }
      const last = state.messages[state.messages.length - 1];
      if (
        last?.role === "assistant" &&
        !Number.isFinite(last.elapsed_ms) &&
        Number.isFinite(requestStartedAt)
      ) {
        last.elapsed_ms = Math.round(performance.now() - requestStartedAt);
      }
      setBusy(false);
    }
  }

  function handleSse(payload) {
    if (payload.session_id) {
      state.currentId = payload.session_id;
    }
    if (payload.type === "started" && payload.title) {
      const existing = state.sessions.find((s) => s.id === state.currentId);
      if (existing) {
        existing.title = payload.title;
      } else if (state.currentId) {
        state.sessions = [
          {
            id: state.currentId,
            title: payload.title,
            created: new Date().toISOString(),
          },
          ...state.sessions,
        ];
      }
      renderSessions();
      els.chatTitle.textContent = payload.title;
    }
    if (payload.messages) {
      state.messages = payload.messages;
      syncMessages();
      if (
        (payload.type === "done" || payload.type === "error") &&
        state.project
      ) {
        const lastMsg = payload.messages[payload.messages.length - 1];
        const toolEvents = lastMsg?.tool_events;
        if (toolEvents?.length) {
          if (shouldRefreshExplorerForToolEvents(toolEvents)) {
            refreshExplorer().catch(() => {});
          }
          reloadEditorTabsForToolEvents(toolEvents).catch(() => {});
        }
      }
    }
    if (payload.sessions) {
      applySessionList(payload.sessions);
    }
    if (payload.usage) {
      setContextUsed(payload.usage);
    }
    if (payload.type === "error" && payload.message) {
      els.logStatus.textContent = `Error: ${payload.message}`;
    }
  }

  function composerMetrics() {
    const el = els.composer;
    const style = getComputedStyle(el);
    let lineHeight = parseFloat(style.lineHeight);
    if (!Number.isFinite(lineHeight)) {
      const fontSize = parseFloat(style.fontSize) || 14;
      lineHeight = fontSize * 1.625;
    }
    const padY =
      (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0);
    const borderY =
      (parseFloat(style.borderTopWidth) || 0) +
      (parseFloat(style.borderBottomWidth) || 0);
    const minH = Math.ceil(lineHeight + padY + borderY);
    const maxH = Math.ceil(lineHeight * 3 + padY + borderY);
    return { minH, maxH };
  }

  function autoResize() {
    const el = els.composer;
    const { minH, maxH } = composerMetrics();
    // Collapse first so scrollHeight tracks actual content (grow and shrink).
    el.style.height = "0px";
    el.style.overflowY = "hidden";
    const contentH = el.scrollHeight;
    const next = Math.min(Math.max(contentH, minH), maxH);
    el.style.height = `${next}px`;
    el.style.overflowY = contentH > maxH ? "auto" : "hidden";
  }

  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(els.composer.value);
  });

  els.composer.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(els.composer.value);
    }
  });
  els.composer.addEventListener("input", autoResize);
  els.messages.addEventListener(
    "scroll",
    () => {
      state.autoScrollMessages = nearBottom();
    },
    { passive: true }
  );
  els.messages.addEventListener(
    "error",
    (e) => {
      const img = e.target;
      if (!(img instanceof HTMLImageElement) || !img.classList.contains("md-image")) return;
      img.classList.add("md-image-broken");
      img.removeAttribute("src");
      img.closest(".md-image-preview-btn")?.classList.add("md-image-broken");
    },
    true
  );
  els.messages.addEventListener("click", handleImageLightboxClick);
  els.messageList.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-copy-btn]");
    if (!btn || btn.disabled) return;
    const text = btn.dataset.copyText || "";
    if (!text) return;
    copyMessageText(text, btn);
  });
  els.lightboxBackdrop?.addEventListener("click", closeImageLightbox);
  els.lightboxClose?.addEventListener("click", closeImageLightbox);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && els.lightbox && !els.lightbox.classList.contains("hidden")) {
      closeImageLightbox();
    }
  });
  els.composer.addEventListener("paste", (e) => {
    handleComposerPaste(e).catch((err) => {
      showComposerStatus(err.message || String(err), "error");
    });
  });

  if (els.composerWrap) {
    els.composerWrap.addEventListener("dragenter", handleComposerDragEnter);
    els.composerWrap.addEventListener("dragover", handleComposerDragOver);
    els.composerWrap.addEventListener("dragleave", handleComposerDragLeave);
    els.composerWrap.addEventListener("drop", (e) => {
      handleComposerDrop(e).catch((err) => {
        showComposerStatus(err.message || String(err), "error");
      });
    });
  }

  // Reset value on click so choosing the same file again still fires `change`.
  els.btnAttachImage.addEventListener("click", () => {
    if (!state.busy) els.inputImage.value = "";
  });
  els.btnAttachFile.addEventListener("click", () => {
    if (!state.busy) els.inputFile.value = "";
  });
  els.inputImage.addEventListener("change", () => {
    addFiles(els.inputImage.files, "image").catch((err) => {
      showComposerStatus(err.message || String(err), "error");
    });
  });
  els.inputFile.addEventListener("change", () => {
    addFiles(els.inputFile.files, "file").catch((err) => {
      showComposerStatus(err.message || String(err), "error");
    });
  });

  if (els.btnSkills) {
    els.btnSkills.addEventListener("click", (e) => {
      e.stopPropagation();
      if (state.busy) return;
      setSkillsMenuOpen(!state.skillsMenuOpen);
    });
  }
  document.addEventListener("click", (e) => {
    if (!state.skillsMenuOpen || !els.skillsMenuWrap) return;
    if (!els.skillsMenuWrap.contains(e.target)) {
      setSkillsMenuOpen(false);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.skillsMenuOpen) {
      setSkillsMenuOpen(false);
    }
  });
  window.addEventListener(
    "resize",
    () => {
      if (state.skillsMenuOpen) positionSkillsMenu();
    },
    { passive: true }
  );
  window.addEventListener(
    "scroll",
    () => {
      if (state.skillsMenuOpen) positionSkillsMenu();
    },
    { passive: true, capture: true }
  );

  els.btnStop.addEventListener("click", () => stopGeneration());
  if (els.toolsToggle) {
    els.toolsToggle.addEventListener("click", () => {
      setToolsExpanded(!state.toolsExpanded);
    });
  }
  if (els.chatsToggle) {
    els.chatsToggle.addEventListener("click", () => {
      setChatsExpanded(!state.chatsExpanded);
    });
  }
  setChatsExpanded(state.chatsExpanded);
  els.btnNew.addEventListener("click", () => newChat());
  els.btnDelete.addEventListener("click", () => showDeleteConfirm());
  els.btnConfirmDelete.addEventListener("click", () => confirmDelete());
  els.btnCancelDelete.addEventListener("click", () => hideConfirms());
  els.btnClearAll.addEventListener("click", () => showClearConfirm());
  els.btnConfirmClear.addEventListener("click", () => confirmClear());
  els.btnCancelClear.addEventListener("click", () => hideConfirms());
  els.btnOpenLog.addEventListener("click", () => openLog());
  els.btnOpenProject?.addEventListener("click", () => {
    browseAndOpenProject().catch((err) => {
      els.logStatus.textContent = err.message || String(err);
    });
  });
  els.btnExplorerRefresh?.addEventListener("click", () => {
    refreshExplorer().catch((err) => {
      els.logStatus.textContent = err.message || String(err);
    });
  });
  if (els.explorerViewToggle) {
    els.explorerViewToggle.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-view]");
      if (!btn) return;
      setExplorerViewMode(btn.dataset.view);
    });
    syncExplorerViewToggle();
  }

  initPanelResizers();
  initEditorMinimap();

  (async () => {
    // Load each panel independently so chat history isn't blocked by GPU telemetry.
    await Promise.all([
      loadSessions().catch(() => {}),
      loadBasicStatus().catch((err) => {
        els.logStatus.textContent = err.message || String(err);
      }),
      loadRuntimeStatus().catch(() => {}),
    ]);
    setBusy(false);
    autoResize();
    focusComposer();
  })();
})();
