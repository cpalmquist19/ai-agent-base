"""Server-sent event formatting."""

from __future__ import annotations

import json
from typing import Any


def sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
