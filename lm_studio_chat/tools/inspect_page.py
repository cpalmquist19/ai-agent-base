"""Playwright page inspection tool."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from lm_studio_chat.config import (
    INSPECT_PAGE_BOT_CHALLENGE_SNIPPETS,
    INSPECT_PAGE_BOT_CHALLENGE_TITLES,
    INSPECT_PAGE_CONTENT_WAIT_MS,
    INSPECT_PAGE_KEEP_WHEN_FILTERING,
    INSPECT_PAGE_MAX_CHARS,
    INSPECT_PAGE_TIMEOUT_MS,
)
from lm_studio_chat.state import AppState

def _playwright_install_hint() -> str:
    return "pip install playwright && playwright install chromium"


def inspect_page_available() -> tuple[bool, str | None]:
    """Check if inspect_page dependencies are installed."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False, f"Requires playwright ({_playwright_install_hint()})"
    return True, None


def _inspect_page_headless() -> bool:
    headed = os.getenv("LM_STUDIO_INSPECT_PAGE_HEADED", "").strip().lower()
    return headed not in ("1", "true", "yes")


def _detect_bot_challenge(title: str, snapshot: str, body_text: str) -> bool:
    title_l = (title or "").lower()
    if any(marker in title_l for marker in INSPECT_PAGE_BOT_CHALLENGE_TITLES):
        return True
    combined = f"{snapshot}\n{body_text}".lower()
    return any(marker in combined for marker in INSPECT_PAGE_BOT_CHALLENGE_SNIPPETS)


def _wait_for_inspect_ready(
    page, timeout_ms: int, state: AppState
) -> tuple[str, bool]:
    """Wait for inspectable UI. Returns (status note, bot_challenge_detected)."""
    if _detect_bot_challenge(page.title(), "", ""):
        return "bot-challenge title detected before wait", True

    role_wait_ms = max(2500, timeout_ms // 6)
    for role in ("textbox", "button", "link", "heading", "checkbox"):
        if state.cancel.is_set():
            return "cancelled", False
        try:
            page.get_by_role(role).first.wait_for(state="visible", timeout=role_wait_ms)
            return f"{role} visible", False
        except Exception:
            continue

    css_wait_ms = max(2000, timeout_ms // 5)
    for selector in ("input:visible", "button:visible", "form:visible", "a[href]:visible"):
        if state.cancel.is_set():
            return "cancelled", False
        try:
            page.locator(selector).first.wait_for(state="visible", timeout=css_wait_ms)
            return f"{selector} visible", False
        except Exception:
            continue

    try:
        page.wait_for_function(
            """() => {
                const text = (document.body?.innerText || '').trim();
                return text.length > 40;
            }""",
            timeout=min(8000, timeout_ms),
        )
    except Exception:
        return "timed out waiting for interactive elements or body text", False

    body_text = ""
    try:
        body_text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        pass
    if _detect_bot_challenge(page.title(), "", body_text):
        return "bot-challenge body text detected", True
    return "body text present (no interactive roles yet)", False


def _filter_aria_snapshot_interactive(snapshot: str) -> str:
    """Keep interactive roles (and headings) from a YAML accessibility tree."""
    kept: list[str] = []
    for line in snapshot.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("- "):
            continue
        match = re.match(r"-\s+(\w+)", stripped)
        if match and match.group(1) in INSPECT_PAGE_KEEP_WHEN_FILTERING:
            kept.append(line)
    return "\n".join(kept)


def _inspect_page_scope_target(page, scope: str) -> tuple[Any, str, bool]:
    """Return (snapshot target, scope label, whether to filter to interactive roles)."""
    scope = (scope or "main").strip().lower()
    if scope not in ("main", "form", "full"):
        scope = "main"

    if scope == "full":
        return page, "full page", True

    if scope == "form":
        form = page.locator("form").first
        if form.count() > 0:
            return form, "form", False
        return (
            page,
            "full page (no form landmark; filtered to interactive roles)",
            True,
        )

    for loc in (
        page.get_by_role("main"),
        page.locator("main"),
        page.locator('[role="main"]'),
    ):
        if loc.count() > 0:
            return loc.first, "main", False
    return (
        page,
        "full page (no main landmark; filtered to interactive roles)",
        True,
    )


def tool_inspect_page(
    state: AppState,
    url: str,
    scope: str = "main",
    max_chars: int = INSPECT_PAGE_MAX_CHARS,
) -> str:
    """Render a URL in headless Chromium and return its accessibility tree."""
    url = (url or "").strip()
    if not url:
        return "Error: url is required."
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        return "Error: url must start with http:// or https://"

    try:
        max_chars = int(max_chars)
    except (TypeError, ValueError):
        max_chars = INSPECT_PAGE_MAX_CHARS
    max_chars = max(2000, min(max_chars, 80_000))

    if state.cancel.is_set():
        return "Error: inspect_page cancelled."

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return (
            "Error: inspect_page requires playwright. "
            f"Install with: {_playwright_install_hint()}"
        )

    snapshot = ""
    final_url = url
    title = ""
    scope_label = scope
    http_status: int | None = None
    wait_note = ""
    body_preview = ""
    bot_challenge = False
    raw_snapshot = ""

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=_inspect_page_headless(),
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 720},
                    locale="en-US",
                )
                page = context.new_page()
                page.set_default_timeout(INSPECT_PAGE_TIMEOUT_MS)
                response = page.goto(url, wait_until="domcontentloaded")
                if response is not None:
                    http_status = response.status
                page.wait_for_load_state("load")

                wait_note, bot_challenge = _wait_for_inspect_ready(
                    page, INSPECT_PAGE_CONTENT_WAIT_MS, state
                )

                final_url = page.url
                title = (page.title() or "").strip()
                try:
                    body_preview = page.locator("body").inner_text(timeout=5000).strip()
                    if len(body_preview) > 300:
                        body_preview = body_preview[:297] + "..."
                except Exception:
                    body_preview = ""

                target, scope_label, filter_interactive = _inspect_page_scope_target(
                    page, scope
                )
                raw_snapshot = (target.aria_snapshot() or "").strip()
                snapshot = raw_snapshot
                if filter_interactive:
                    filtered = _filter_aria_snapshot_interactive(raw_snapshot)
                    if filtered.strip():
                        snapshot = filtered
                    elif raw_snapshot:
                        scope_label += " (no interactive roles matched filter; raw tree kept)"
                if _detect_bot_challenge(title, raw_snapshot, body_preview):
                    bot_challenge = True
            finally:
                browser.close()
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" in msg or "BrowserType.launch" in msg:
            return (
                "Error: Chromium browser binaries not installed. "
                "Run: playwright install chromium\n\n"
                f"Details: {msg}"
            )
        if "timeout" in msg.lower():
            return (
                f"Error: timed out loading {url} "
                f"(limit {INSPECT_PAGE_TIMEOUT_MS}ms).\n\nDetails: {msg}"
            )
        return f"Error inspecting {url}: {msg}"

    if state.cancel.is_set():
        return "Error: inspect_page cancelled."

    snapshot = (snapshot or "").strip()
    if not snapshot:
        lines = [
            f"Inspected: {final_url}",
            f"Scope: {scope_label}",
            *( [f"HTTP status: {http_status}"] if http_status is not None else [] ),
            *( [f"Title: {title}"] if title else [] ),
            *( [f"Wait: {wait_note}"] if wait_note else [] ),
        ]
        if body_preview:
            lines.append(f"Visible body text: {json.dumps(body_preview)}")
        lines.append("")
        if bot_challenge:
            lines.extend(
                [
                    "Bot/WAF challenge detected — headless Chromium was blocked or is "
                    "still on a challenge page.",
                    "",
                    "Headless Chromium uses your OS network stack (Cloudflare WARP "
                    "applies if active system-wide). Some WAF rules block automated "
                    "browsers even when your normal browser works.",
                    "",
                    "Try: ensure WARP is connected, set LM_STUDIO_INSPECT_PAGE_HEADED=1 "
                    "and retry, or run Playwright codegen in the user's project.",
                ]
            )
        else:
            lines.extend(
                [
                    "No accessibility tree captured after waiting for the page to render.",
                    "Common causes: SPA still hydrating, login UI in an iframe/shadow "
                    "root, or auth redirect with no exposed roles.",
                    "",
                    "Try inspect_page again with scope='form' or scope='full'. Do not "
                    "invent selectors.",
                ]
            )
        return "\n".join(lines)

    sections = [
        f"Inspected: {final_url}",
        f"Scope: {scope_label}",
        *( [f"HTTP status: {http_status}"] if http_status is not None else [] ),
        *( [f"Title: {title}"] if title else [] ),
        *( [f"Wait: {wait_note}"] if wait_note else [] ),
        (
            "Source: Playwright accessibility tree (aria_snapshot). "
            "Use ONLY elements below; do not invent selectors."
        ),
        (
            "Locator mapping: getByRole(role, { name }) for role lines; "
            "getByTestId when test ids appear; getByLabel/getByPlaceholder "
            "for form fields as needed."
        ),
        "---",
        "Accessibility tree:",
        snapshot,
    ]
    body = "\n".join(sections)
    if len(body) > max_chars:
        body = (
            body[:max_chars]
            + f"\n... (truncated at {max_chars} chars; narrow scope or reduce page size)"
        )
    return body


