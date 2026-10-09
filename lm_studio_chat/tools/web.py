"""Web search and URL fetch tools."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from typing import Any

from lm_studio_chat.config import (
    FETCH_URL_MAX_CHARS,
    FETCH_URL_TIMEOUT_SECONDS,
    FETCH_URL_USER_AGENT,
    WEB_SEARCH_RESULT_LIMIT,
)

def import_ddgs():
    """Prefer the renamed `ddgs` package; fall back to `duckduckgo_search`."""
    try:
        from ddgs import DDGS  # type: ignore

        return DDGS
    except ImportError:
        pass
    try:
        from duckduckgo_search import DDGS  # type: ignore

        return DDGS
    except ImportError as exc:
        raise ImportError(
            "DuckDuckGo search requires the `ddgs` package. "
            "Install with: pip install ddgs"
        ) from exc


def web_search_available() -> tuple[bool, str | None]:
    """Check if web_search dependencies are installed."""
    try:
        import_ddgs()
        return True, None
    except ImportError:
        return False, "Requires ddgs package (pip install ddgs)"


def tool_web_search(
    query: str,
    max_results: int = 5,
    region: str = "us-en",
) -> str:
    """Search the web via DuckDuckGo and return titled snippets with URLs."""
    query = (query or "").strip()
    if not query:
        return "Error: query is required."

    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, min(max_results, WEB_SEARCH_RESULT_LIMIT))

    try:
        DDGS = import_ddgs()
    except ImportError as exc:
        return f"Error: {exc}"

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    # Prefer DuckDuckGo; fall back to ddgs auto backends if that returns nothing.
    for backend in ("duckduckgo", None):
        try:
            kwargs: dict[str, Any] = {
                "region": region or "us-en",
                "max_results": max_results,
            }
            if backend:
                kwargs["backend"] = backend
            results = list(DDGS().text(query, **kwargs) or [])
        except Exception as exc:
            errors.append(f"{backend or 'auto'}: {exc}")
            results = []
        if results:
            break

    if not results:
        detail = f" ({'; '.join(errors)})" if errors else ""
        return f"No DuckDuckGo results for: {query}{detail}"

    lines = [
        f"Web search results for: {query}\n",
        "NOTE: These are short search snippets only — not full page content. "
        "Do not invent missing details. Use fetch_url on a result URL when you "
        "need specific facts from the page.\n",
    ]
    for i, item in enumerate(results, start=1):
        title = (item.get("title") or "(no title)").strip()
        url = (item.get("href") or item.get("link") or "").strip()
        body = (item.get("body") or item.get("snippet") or "").strip()
        lines.append(f"{i}. {title}")
        if url:
            lines.append(f"   URL: {url}")
        if body:
            lines.append(f"   {body}")
        lines.append("")
    return "\n".join(lines).rstrip()


# Structural tags that almost never hold the primary answer/content.
_BOILERPLATE_TAGS = (
    "script", "style", "noscript", "svg", "template", "nav", "header",
    "footer", "aside", "form", "button", "input", "select", "textarea",
    "label", "iframe", "dialog", "figure",
)

# Whole-token id/class/role markers for chrome, ads, and navigation. Matched
# against tokens (split on non-alphanumerics) so "read"/"header" don't trip
# an "ad"/"head" substring false-positive.
_BOILERPLATE_TOKENS = frozenset({
    "nav", "navbar", "navigation", "menu", "menubar", "topbar", "sidebar",
    "sidebars", "footer", "footers", "header", "headers", "masthead",
    "cookie", "cookies", "consent", "gdpr", "banner", "banners",
    "ad", "ads", "advert", "adverts", "advertisement", "advertising",
    "promo", "promotion", "sponsor", "sponsored", "social", "share",
    "sharing", "newsletter", "subscribe", "signup", "comment", "comments",
    "related", "recommended", "recommendation", "recommendations",
    "breadcrumb", "breadcrumbs", "pagination", "pager", "modal", "popup",
    "overlay", "skip", "skiplink", "hidden", "offscreen", "sr", "visually",
})


def _looks_like_boilerplate(tag) -> bool:
    """True if a tag's id/class/role tokens mark it as chrome/ads/nav."""
    identifiers: list[str] = []
    cls = tag.get("class")
    if cls:
        identifiers.extend(cls)
    for attr in ("id", "role"):
        val = tag.get(attr)
        if val:
            identifiers.append(val)
    for raw in identifiers:
        for token in re.split(r"[^a-z0-9]+", str(raw).lower()):
            if token and token in _BOILERPLATE_TOKENS:
                return True
    return False


def _html_extract_meta(html: str) -> tuple[str, str]:
    """Return (title, description) from the page's <title>/meta tags."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return "", ""

    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            title = og["content"].strip()

    description = ""
    for attrs in (
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"},
    ):
        meta = soup.find("meta", attrs=attrs)
        if meta and meta.get("content"):
            description = meta["content"].strip()
            break
    return title, description


def _pick_main_region(soup):
    """Return the largest plausible main-content region, or None."""
    candidates = []
    candidates.extend(soup.find_all("main"))
    candidates.extend(soup.find_all(attrs={"role": "main"}))
    candidates.extend(soup.find_all("article"))
    if not candidates:
        return None
    best = max(candidates, key=lambda t: len(t.get_text(strip=True)))
    # Only trust it if it actually holds a meaningful amount of text.
    return best if len(best.get_text(strip=True)) >= 200 else None


def _html_to_text(html: str) -> str:
    """Extract the main readable content from HTML, dropping site chrome.

    Order of preference:
      1. trafilatura (readability-grade extraction) when installed.
      2. BeautifulSoup with boilerplate removal + main-region targeting.
      3. Regex tag stripping as a last resort.
    """
    # 1. Best-in-class extractor when available.
    try:
        import trafilatura  # type: ignore

        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )
        if extracted and extracted.strip():
            return _normalize_lines(extracted)
    except Exception:
        pass

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        BeautifulSoup = None  # type: ignore[misc, assignment]

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")

        # Drop obvious non-content tags outright.
        for tag in soup(_BOILERPLATE_TAGS):
            tag.decompose()

        # Drop elements flagged as chrome/ads/nav by their id/class/role.
        for tag in soup.find_all(True):
            if getattr(tag, "decomposed", False):
                continue
            if _looks_like_boilerplate(tag):
                tag.decompose()

        # Prefer the main content region; fall back to <body>, then whole doc.
        root = _pick_main_region(soup) or soup.body or soup
        text = root.get_text(separator="\n")
    else:
        # Minimal fallback: strip tags without BeautifulSoup.
        text = re.sub(
            r"(?is)<(script|style|noscript|svg|template|nav|header|footer|aside|form)\b[^>]*>.*?</\1>",
            " ",
            html,
        )
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;|&#160;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)

    return _normalize_lines(text)


def _normalize_lines(text: str) -> str:
    """Trim whitespace, collapse blank runs, and drop consecutive dupes."""
    lines = [ln.strip() for ln in text.splitlines()]
    cleaned: list[str] = []
    blank = False
    prev = None
    for ln in lines:
        if not ln:
            if not blank and cleaned:
                cleaned.append("")
            blank = True
            continue
        # Collapse consecutive identical lines (e.g. repeated nav labels).
        if ln == prev:
            continue
        cleaned.append(ln)
        prev = ln
        blank = False
    return "\n".join(cleaned).strip()


def _http_get(url: str, byte_budget: int) -> tuple[str, str, bytes] | str:
    """Fetch a URL; return (final_url, content_type, raw_bytes) or an error string."""
    url = (url or "").strip()
    if not url:
        return "Error: url is required."
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        return "Error: url must start with http:// or https://"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": FETCH_URL_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=FETCH_URL_TIMEOUT_SECONDS) as resp:
            final_url = resp.geturl()
            content_type = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read(max(4096, byte_budget))
    except urllib.error.HTTPError as exc:
        return f"Error fetching {url}: HTTP {exc.code} {exc.reason}"
    except urllib.error.URLError as exc:
        return f"Error fetching {url}: {exc.reason}"
    except TimeoutError:
        return f"Error fetching {url}: timed out after {FETCH_URL_TIMEOUT_SECONDS}s"
    except Exception as exc:
        return f"Error fetching {url}: {exc}"
    return final_url, content_type, raw


def _decode_http_body(raw: bytes, content_type: str) -> str:
    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")




def tool_fetch_url(url: str, max_chars: int = FETCH_URL_MAX_CHARS) -> str:
    """Fetch a URL and return extracted plain text for grounded answering."""
    url = (url or "").strip()
    if not url:
        return "Error: url is required."
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        return "Error: url must start with http:// or https://"

    try:
        max_chars = int(max_chars)
    except (TypeError, ValueError):
        max_chars = FETCH_URL_MAX_CHARS
    max_chars = max(500, min(max_chars, 50_000))

    fetched = _http_get(url, byte_budget=max_chars * 4 + 4096)
    if isinstance(fetched, str):
        return fetched
    final_url, content_type, raw = fetched
    html = _decode_http_body(raw, content_type)

    is_html = (
        "html" in content_type
        or "<html" in html[:500].lower()
        or "<!doctype" in html[:200].lower()
    )
    title = description = ""
    if is_html:
        title, description = _html_extract_meta(html)
        body = _html_to_text(html)
    else:
        body = html.strip()

    if not body:
        note_lines = [
            f"Fetched: {final_url}",
            f"Content-Type: {content_type or '(unknown)'}",
        ]
        if title:
            note_lines.append(f"Title: {title}")
        if description:
            note_lines.append(f"Description: {description}")
        note_lines.append(
            "No readable body text extracted (page may be JS-rendered or "
            "blocked). Report only the Title/Description above if relevant."
        )
        return "\n".join(note_lines)

    truncated = len(body) > max_chars
    if truncated:
        body = body[:max_chars]

    header_lines = [
        f"Fetched: {final_url}",
        f"Content-Type: {content_type or '(unknown)'}",
    ]
    if title:
        header_lines.append(f"Title: {title}")
    if description:
        header_lines.append(f"Description: {description}")
    header_lines.append(
        f"{'(truncated) ' if truncated else ''}"
        "Use ONLY facts present below. Do not invent missing details."
    )
    header_lines.append("---")
    return "\n".join(header_lines) + "\n" + body
