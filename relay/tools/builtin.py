"""Built-in utility tools (time, math)."""

from __future__ import annotations

import ast
import datetime as _dt
import math
import operator
from typing import Any


def tool_get_current_time() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS: dict[str, Any] = {k: getattr(math, k) for k in dir(math) if callable(getattr(math, k)) and not k.startswith("_")}
_FUNCTIONS.update({"abs": abs, "round": round, "min": min, "max": max, "pow": pow})
_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf, "nan": math.nan}

_MAX_EXPONENT = 1000  # keeps 9**9**9 from freezing the app
_MAX_FACTORIAL_ARG = 5000
_MAX_NODES = 200


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError(f"exponent too large (limit {_MAX_EXPONENT})")
        return _BINARY_OPS[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS and not node.keywords:
        args = [_eval_node(a) for a in node.args]
        if node.func.id in ("factorial", "comb", "perm") and any(abs(a) > _MAX_FACTORIAL_ARG for a in args):
            raise ValueError(f"argument too large for {node.func.id} (limit {_MAX_FACTORIAL_ARG})")
        if node.func.id == "pow" and len(args) >= 2 and abs(args[1]) > _MAX_EXPONENT:
            raise ValueError(f"exponent too large (limit {_MAX_EXPONENT})")
        return _FUNCTIONS[node.func.id](*args)
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def tool_calculate(expression: str) -> str:
    """Evaluate arithmetic with +, -, *, /, //, %, ** and the functions in `math`.

    Parsed with `ast`, never `eval`: only numbers, a few constants, arithmetic and
    whitelisted function calls are accepted. Attribute access, names, subscripts,
    comprehensions and imports are rejected, so model- or web-supplied text cannot run code.
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
            raise ValueError("expression too complex")
        return str(_eval_node(tree.body))
    except Exception as exc:
        return f"Error: {exc}"
