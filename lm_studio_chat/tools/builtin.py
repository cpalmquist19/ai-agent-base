"""Built-in utility tools (time, math)."""

from __future__ import annotations

import datetime as _dt
import math


def tool_get_current_time() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def tool_calculate(expression: str) -> str:
    """Evaluate a math expression using only the `math` module + basic builtins."""
    allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    allowed.update({"abs": abs, "round": round, "min": min, "max": max, "pow": pow})
    try:
        return str(eval(expression, {"__builtins__": {}}, allowed))
    except Exception as exc:
        return f"Error: {exc}"
