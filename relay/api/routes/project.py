"""Project open/close, explorer, and file-serving routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from relay.config import (
    IMAGE_MIME_BY_EXT,
    MAX_IMAGE_ATTACHMENT_BYTES,
    MAX_TEXT_ATTACHMENT_BYTES,
)
from relay.models import BrowseProjectRequest, OpenProjectRequest
from relay.project.explorer import (
    attachable_project_file_kind,
    attachment_ext_from_name,
    explorer_entries,
)
from relay.project.root import (
    clear_project_root,
    pick_folder_dialog,
    resolve_project_child,
    set_project_root,
)
from relay.state import AppState


def create_project_router(state: AppState) -> APIRouter:
    router = APIRouter()

    @router.get("/api/project")
    def api_get_project() -> dict[str, Any]:
        if state.project_root is None:
            return {"project": None}
        return {
            "project": {
                "root": str(state.project_root),
                "name": state.project_root.name,
            }
        }

    @router.post("/api/project/browse")
    def api_browse_project(body: BrowseProjectRequest | None = None) -> dict[str, Any]:
        initial: Path | None = state.project_root
        if body and body.initial_path:
            try:
                candidate = Path(body.initial_path).expanduser().resolve()
                if candidate.is_dir():
                    initial = candidate
            except OSError:
                pass
        selected = pick_folder_dialog(initial)
        if not selected:
            raise HTTPException(status_code=400, detail="Folder selection cancelled")
        return {"path": selected}

    @router.post("/api/project/open")
    def api_open_project(body: OpenProjectRequest) -> dict[str, Any]:
        try:
            resolved = set_project_root(state, Path(body.path))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "project": {
                "root": str(resolved),
                "name": resolved.name,
            },
            "cwd": str(state.shell_cwd),
            "entries": explorer_entries(state, ""),
        }

    @router.post("/api/project/close")
    def api_close_project() -> dict[str, str]:
        clear_project_root(state)
        return {"ok": True}

    @router.get("/api/project/entries")
    def api_project_entries(path: str = Query(default="")) -> dict[str, Any]:
        if state.project_root is None:
            raise HTTPException(status_code=400, detail="No project is open")
        try:
            entries = explorer_entries(state, path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        rel = path.replace("\\", "/").strip("/")
        return {
            "path": rel,
            "entries": entries,
            "project": {
                "root": str(state.project_root),
                "name": state.project_root.name,
            },
        }

    @router.get("/api/project/file")
    def api_project_file(path: str = Query(..., min_length=1)) -> FileResponse:
        """Serve an attachable project file for explorer drag-and-drop."""
        if state.project_root is None:
            raise HTTPException(status_code=400, detail="No project is open")
        try:
            target = resolve_project_child(state, path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        kind = attachable_project_file_kind(target.name)
        if kind is None:
            raise HTTPException(status_code=403, detail=f"Blocked file type: {target.name}")
        size = target.stat().st_size
        ext = attachment_ext_from_name(target.name)
        if kind == "image":
            if size > MAX_IMAGE_ATTACHMENT_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image too large (max {MAX_IMAGE_ATTACHMENT_BYTES // (1024 * 1024)} MB)",
                )
            mime = IMAGE_MIME_BY_EXT.get(ext, "application/octet-stream")
        else:
            if size > MAX_TEXT_ATTACHMENT_BYTES:
                raise HTTPException(status_code=400, detail="File too large (max 512 KB)")
            mime = "text/plain"
        return FileResponse(
            target,
            media_type=mime,
            filename=target.name,
            headers={"Cache-Control": "no-store"},
        )

    return router
