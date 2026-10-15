"""Status, skills, and runtime telemetry routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from relay.config import (
    IMAGE_MIME_BY_EXT,
    MAX_TOKENS,
    TEMPERATURE,
)
from relay.lm_client import (
    effective_context_window,
    fetch_context_capacity,
    fetch_gpu_status,
)
from relay.skills.discovery import skills_catalog
from relay.state import AppState
from relay.tools.registry import tool_catalog


def create_status_router(state: AppState) -> APIRouter:
    router = APIRouter()

    @router.get("/api/status")
    def api_status() -> dict[str, Any]:
        """Fast snapshot: in-memory model, cwd, and tool catalog."""
        project = None
        if state.project_root is not None:
            project = {
                "root": str(state.project_root),
                "name": state.project_root.name,
            }
        return {
            "provider": state.provider.id,
            "provider_label": state.provider.label,
            "local": state.provider.local,
            "supports_vision": getattr(state.provider, "supports_vision", False),
            "model": state.model_id or "unknown",
            "cwd": str(state.shell_cwd),
            "project": project,
            "tools": tool_catalog(),
            "skills": skills_catalog(),
            "base_url": state.provider.base_url,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
        }

    @router.get("/api/skills")
    def api_skills() -> dict[str, Any]:
        return {"skills": skills_catalog()}

    @router.get("/api/status/runtime")
    def api_status_runtime() -> dict[str, Any]:
        """Slower telemetry from LM Studio, nvidia-smi, and the lms CLI."""
        if not state.provider.local:
            return {
                "context_length": None,
                "max_context_length": None,
                "gpu": None,
            }
        caps = fetch_context_capacity(state.model_id)
        ctx_win = effective_context_window(caps)
        if ctx_win is not None:
            state.context_window = ctx_win
        return {
            "context_length": ctx_win,
            "max_context_length": caps.get("max") if caps else None,
            "gpu": fetch_gpu_status(state.model_id),
        }

    @router.get("/api/local-file")
    def api_local_file(path: str = Query(..., min_length=1)) -> FileResponse:
        """Serve a local image file referenced in markdown (e.g. screenshot paths)."""
        cleaned = path.strip().strip('"').strip("'")
        try:
            candidate = Path(cleaned).expanduser()
            if not candidate.is_absolute():
                candidate = (state.shell_cwd / candidate).resolve()
            else:
                candidate = candidate.resolve()
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid path: {exc}") from exc
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        mime = IMAGE_MIME_BY_EXT.get(candidate.suffix.lower())
        if mime is None:
            raise HTTPException(status_code=403, detail="Only image files are supported")
        return FileResponse(candidate, media_type=mime, filename=candidate.name)

    return router
