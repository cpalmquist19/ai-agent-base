"""Agent skill discovery, listing, and loading."""

from __future__ import annotations

import json
import os
from pathlib import Path

from lm_studio_chat.config import _APP_ROOT, _DEFAULT_SKILLS_DIRS, _SKILL_FRONTMATTER_RE
from lm_studio_chat.types import SkillEntry


def skill_search_dirs() -> list[Path]:
    sep = ";" if os.name == "nt" else ":"
    dirs = list(_DEFAULT_SKILLS_DIRS)
    extra = os.getenv("LM_STUDIO_SKILLS_DIRS", "")
    for part in extra.split(sep):
        part = part.strip()
        if part:
            dirs.append(Path(part).expanduser())
    seen: set[str] = set()
    unique: list[Path] = []
    for d in dirs:
        key = str(d.expanduser())
        if key not in seen:
            seen.add(key)
            unique.append(d.expanduser())
    return unique


def parse_skill_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _SKILL_FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip()] = val.strip().strip("\"'")
    body = text[match.end() :]
    return meta, body


def discover_skills() -> list[SkillEntry]:
    entries: list[SkillEntry] = []
    seen_names: set[str] = set()
    for base in skill_search_dirs():
        if not base.is_dir():
            continue
        for skill_dir in sorted(base.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                raw = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            meta, _body = parse_skill_frontmatter(raw)
            name = (meta.get("name") or skill_dir.name).strip()
            description = (meta.get("description") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            entries.append(
                SkillEntry(
                    name=name,
                    description=description,
                    path=skill_md,
                    skill_dir=skill_dir,
                )
            )
    return entries


def tool_read_skill(name: str) -> str:
    """Load the full instructions for a named agent skill."""
    name = (name or "").strip()
    if not name:
        return "Error: name is required."
    entries = discover_skills()
    match = next((e for e in entries if e.name.lower() == name.lower()), None)
    if match is None:
        available = ", ".join(e.name for e in entries) or "(none installed)"
        return f"Error: unknown skill '{name}'. Available: {available}"
    try:
        content = match.path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading skill {match.name}: {exc}"

    extras = sorted(
        f.name
        for f in match.skill_dir.iterdir()
        if f.is_file() and f.name != "SKILL.md"
    )
    lines = [content.rstrip()]
    if extras:
        lines.append("\n---")
        lines.append(
            "Additional files in this skill directory (read with read_file when needed):"
        )
        for fn in extras:
            lines.append(f"- {match.skill_dir / fn}")
    return "\n".join(lines) + "\n"


def tool_list_skills() -> str:
    """List all available Agent Skills (name + description)."""
    entries = discover_skills()
    if not entries:
        return (
            "No Agent Skills installed. Skills live in folders with SKILL.md under "
            f"{_APP_ROOT / 'skills'} or ~/.lm_studio_chat/skills/. "
            "Call read_skill(name) after skills are added."
        )
    lines = [
        f"{len(entries)} Agent Skill(s) available. "
        "Call read_skill(name) to load full instructions before following a skill.",
        "---",
    ]
    for entry in entries:
        desc = entry.description or "(no description)"
        lines.append(f"- {entry.name}: {desc}")
    return "\n".join(lines)


def skill_api_prefix(skill_name: str) -> str:
    quoted = json.dumps(skill_name)
    return (
        f"[Agent Skill selected: {skill_name}]\n"
        f"The user chose this skill for this message. Call read_skill({quoted}) "
        f"first, then follow its workflow step by step.\n\n"
    )


def resolve_skill_name(skill_name: str) -> str | None:
    """Return canonical skill name if it exists, else None."""
    name = (skill_name or "").strip()
    if not name:
        return None
    match = next(
        (e.name for e in discover_skills() if e.name.lower() == name.lower()),
        None,
    )
    return match


def skills_catalog() -> list[dict[str, str]]:
    return [
        {"name": s.name, "description": s.description}
        for s in discover_skills()
    ]
