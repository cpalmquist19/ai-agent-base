"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from relay.api.routes.chat import create_chat_router
from relay.api.routes.project import create_project_router
from relay.api.routes.sessions import create_sessions_router
from relay.api.routes.status import create_status_router
from relay.config import STATIC_DIR
from relay.state import AppState


def create_app(state: AppState) -> FastAPI:
    app = FastAPI(title="Relay")
    app.state.app_state = state

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=500, detail="static/index.html missing")
        return FileResponse(index_path)

    app.include_router(create_status_router(state))
    app.include_router(create_project_router(state))
    app.include_router(create_sessions_router(state))
    app.include_router(create_chat_router(state))

    return app
