"""System prompt construction for chat turns."""

from __future__ import annotations

from lm_studio_chat.config import SYSTEM_PROMPT, VISION_SYSTEM_PROMPT_BLOCK
from lm_studio_chat.skills.discovery import discover_skills
from lm_studio_chat.state import AppState


def build_system_prompt(state: AppState) -> str:
    parts = [SYSTEM_PROMPT]
    if getattr(state.provider, "supports_vision", False):
        parts.append(VISION_SYSTEM_PROMPT_BLOCK)
    cwd = state.shell_cwd.resolve()
    parts.append(f"\nWorking directory (relative paths resolve here): {cwd}")
    if state.project_root is not None:
        parts.append(f"Open project root: {state.project_root.resolve()}")
    skills = discover_skills()
    if skills:
        parts.append(
            "\nAvailable Agent Skills (call read_skill(name) to load full instructions):"
        )
        for skill in skills:
            desc = skill.description or "(no description)"
            parts.append(f"- {skill.name}: {desc}")
    return "\n".join(parts)
