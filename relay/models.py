"""Pydantic models for HTTP request bodies."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatAttachment(BaseModel):
    kind: Literal["image", "file"]
    name: str
    mime: str | None = None
    text: str | None = None
    data_base64: str | None = None


class ChatRequest(BaseModel):
    message: str = ""
    session_id: str | None = None
    attachments: list[ChatAttachment] = Field(default_factory=list)
    skill: str | None = None


class OpenLogRequest(BaseModel):
    session_id: str | None = None


class StopRequest(BaseModel):
    session_id: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)


class OpenProjectRequest(BaseModel):
    path: str = Field(..., min_length=1)


class BrowseProjectRequest(BaseModel):
    initial_path: str | None = None
