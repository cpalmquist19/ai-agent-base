"""LM Studio model discovery, context capacity, and GPU telemetry."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any

from lm_studio_chat.config import LM_STUDIO_BASE_URL

_vram_estimate_cache: dict[str, tuple[float, int | None]] = {}
_VRAM_ESTIMATE_TTL_SEC = 60.0


def native_api_base() -> str:
    """LM Studio's OpenAI base ends in /v1; its native REST API lives at /api/v0."""
    base = LM_STUDIO_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base + "/api/v0"


def fetch_context_capacity(model_id: str | None) -> dict[str, int | None] | None:
    """Return {'loaded': int|None, 'max': int|None} from LM Studio's native API."""
    url = native_api_base() + "/models"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None

    entries = data.get("data") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return None

    def _caps(entry: dict[str, Any]) -> dict[str, int | None]:
        loaded = entry.get("loaded_context_length")
        maximum = entry.get("max_context_length")
        return {
            "loaded": loaded if isinstance(loaded, int) else None,
            "max": maximum if isinstance(maximum, int) else None,
        }

    chosen: dict[str, Any] | None = None
    for entry in entries:
        if isinstance(entry, dict) and model_id and entry.get("id") == model_id:
            chosen = entry
            break
    if chosen is None:
        for entry in entries:
            if isinstance(entry, dict) and entry.get("state") == "loaded":
                chosen = entry
                break
    return _caps(chosen) if chosen is not None else None


def effective_context_window(caps: dict[str, int | None] | None) -> int | None:
    """The window that actually bounds the conversation (loaded, else max)."""
    if not caps:
        return None
    return caps.get("loaded") or caps.get("max")


def model_is_loaded(model_id: str | None) -> bool:
    """Return True when the active (or any) model is loaded in LM Studio."""
    url = native_api_base() + "/models"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return False

    entries = data.get("data") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return False

    if model_id:
        for entry in entries:
            if isinstance(entry, dict) and entry.get("id") == model_id:
                return entry.get("state") == "loaded"
        return False

    return any(
        isinstance(entry, dict) and entry.get("state") == "loaded" for entry in entries
    )


def fetch_gpu_info() -> dict[str, int | str] | None:
    """Return GPU name and VRAM stats from nvidia-smi, or None when unavailable."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        completed = subprocess.run(
            [
                smi,
                "--query-gpu=name,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None

    row = completed.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in row.split(",")]
    if len(parts) < 4:
        return None
    try:
        total_mib = int(parts[1])
        used_mib = int(parts[2])
        free_mib = int(parts[3])
    except ValueError:
        return None

    return {
        "name": parts[0],
        "total_mib": total_mib,
        "used_mib": used_mib,
        "free_mib": free_mib,
    }


def fetch_v1_models() -> list[dict[str, Any]] | None:
    """Return model entries from LM Studio's v1 REST API."""
    base = LM_STUDIO_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    url = base + "/api/v1/models"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return None
    return [entry for entry in models if isinstance(entry, dict)]


def loaded_model_details(model_id: str | None) -> dict[str, Any] | None:
    """Return size/context for the active loaded model, if any."""
    models = fetch_v1_models()
    if not models:
        return None

    chosen: dict[str, Any] | None = None
    for entry in models:
        instances = entry.get("loaded_instances")
        if not isinstance(instances, list) or not instances:
            continue
        instance = instances[0] if isinstance(instances[0], dict) else None
        if instance is None:
            continue
        instance_id = instance.get("id") or entry.get("key")
        if model_id and instance_id != model_id and entry.get("key") != model_id:
            continue
        config = instance.get("config") if isinstance(instance.get("config"), dict) else {}
        size_bytes = entry.get("size_bytes")
        chosen = {
            "key": entry.get("key") or instance_id,
            "size_bytes": size_bytes if isinstance(size_bytes, int) else None,
            "context_length": config.get("context_length")
            if isinstance(config.get("context_length"), int)
            else None,
        }
        if model_id and (instance_id == model_id or entry.get("key") == model_id):
            return chosen

    return chosen


def parse_lms_vram_estimate(text: str) -> int | None:
    """Parse `Estimated GPU Memory: 9.63 GiB` from lms CLI output."""
    match = re.search(
        r"Estimated GPU Memory:\s+([\d.]+)\s*(GiB|MiB|GB|MB)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower()
    if unit in {"gib", "gb"}:
        return int(round(amount * 1024))
    return int(round(amount))


def estimate_model_vram_mib(model_key: str, context_length: int | None) -> int | None:
    """Ask LM Studio CLI for model+context VRAM estimate (cached briefly)."""
    cache_key = f"{model_key}:{context_length or 'default'}"
    now = dt.datetime.now().timestamp()
    cached = _vram_estimate_cache.get(cache_key)
    if cached and (now - cached[0]) < _VRAM_ESTIMATE_TTL_SEC:
        return cached[1]

    lms = shutil.which("lms")
    if not lms:
        _vram_estimate_cache[cache_key] = (now, None)
        return None

    cmd = [lms, "load", "--estimate-only", model_key]
    if context_length:
        cmd.extend(["--context-length", str(context_length)])

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _vram_estimate_cache[cache_key] = (now, None)
        return None

    text = f"{completed.stdout or ''}\n{completed.stderr or ''}"
    estimate_mib = parse_lms_vram_estimate(text)
    _vram_estimate_cache[cache_key] = (now, estimate_mib)
    return estimate_mib


def fetch_gpu_status(model_id: str | None) -> dict[str, Any] | None:
    """GPU telemetry for the context sidebar."""
    gpu = fetch_gpu_info()
    if gpu is None:
        return None

    used_mib = int(gpu["used_mib"])
    total_mib = int(gpu["total_mib"])
    model_loaded = model_is_loaded(model_id)
    details = loaded_model_details(model_id) if model_loaded else None

    weights_mib = 0
    context_mib = 0
    other_mib = used_mib if not model_loaded else 0
    context_length: int | None = None
    estimated_total_mib: int | None = None

    if details:
        context_length = details.get("context_length")
        size_bytes = details.get("size_bytes")
        if isinstance(size_bytes, int) and size_bytes > 0:
            weights_mib = max(1, int(round(size_bytes / (1024 * 1024))))

        model_key = details.get("key")
        if isinstance(model_key, str) and model_key:
            estimated_total_mib = estimate_model_vram_mib(model_key, context_length)

        if weights_mib > 0:
            runtime_mib = max(0, used_mib - weights_mib)
            if estimated_total_mib is not None:
                context_mib = max(0, min(runtime_mib, estimated_total_mib - weights_mib))
            else:
                context_mib = runtime_mib
            other_mib = max(0, used_mib - weights_mib - context_mib)
        else:
            context_mib = max(0, used_mib - other_mib)

    return {
        "name": gpu["name"],
        "total_mib": total_mib,
        "used_mib": used_mib,
        "free_mib": int(gpu["free_mib"]),
        "model_loaded": model_loaded,
        "weights_mib": weights_mib,
        "context_mib": context_mib,
        "other_vram_mib": other_mib,
        "context_length": context_length,
        "estimated_total_mib": estimated_total_mib,
        "model_vram_mib": weights_mib + context_mib,
    }
