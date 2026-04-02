from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter

from config import DEFAULT_MODEL
from services.ollama_async import OllamaResponseError, OllamaUnavailableError, get_ollama_client

router = APIRouter(prefix="/metrics", tags=["metrics"])

LATEST_METRICS: dict[str, float | None | str] = {
    "tok_per_sec": None,
    "ttft_ms": None,
    "model": DEFAULT_MODEL,
}

_MEMORY_SAMPLE: dict[str, float] = {"value": 0.0, "captured_at": 0.0}
_MEMORY_LOCK = asyncio.Lock()


def set_latest_metrics(*, model: str, tok_per_sec: float | None, ttft_ms: float | None) -> None:
    LATEST_METRICS["model"] = model
    LATEST_METRICS["tok_per_sec"] = tok_per_sec
    LATEST_METRICS["ttft_ms"] = ttft_ms


def _parse_vm_stat_output(output: str) -> float:
    page_size = 4096
    pages: dict[str, int] = {}

    for line in output.splitlines():
        if "page size of" in line:
            try:
                page_size = int(line.split("page size of")[1].split("bytes")[0].strip())
            except (IndexError, ValueError):
                page_size = 4096
            continue

        if ":" not in line:
            continue

        name, value = line.split(":", 1)
        clean_value = value.strip().rstrip(".").replace(".", "")
        if clean_value.isdigit():
            pages[name.strip()] = int(clean_value)

    used_pages = (
        pages.get("Pages active", 0)
        + pages.get("Pages wired down", 0)
        + pages.get("Pages occupied by compressor", 0)
    )
    return round((used_pages * page_size) / (1024**3), 2)


async def _sample_memory_gb() -> float:
    now = time.monotonic()
    if now - _MEMORY_SAMPLE["captured_at"] < 1.0:
        return _MEMORY_SAMPLE["value"]

    async with _MEMORY_LOCK:
        now = time.monotonic()
        if now - _MEMORY_SAMPLE["captured_at"] < 1.0:
            return _MEMORY_SAMPLE["value"]

        process = await asyncio.create_subprocess_exec(
            "vm_stat",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        memory_gb = _parse_vm_stat_output(stdout.decode())
        _MEMORY_SAMPLE["value"] = memory_gb
        _MEMORY_SAMPLE["captured_at"] = now
        return memory_gb


@router.get("")
async def get_metrics() -> dict[str, Any]:
    model = str(LATEST_METRICS["model"] or DEFAULT_MODEL)
    try:
        model_loaded = await get_ollama_client().is_model_loaded(model)
    except (OllamaUnavailableError, OllamaResponseError):
        model_loaded = False

    return {
        "ram_used_gb": await _sample_memory_gb(),
        "ram_total_gb": 24,
        "tok_per_sec": (
            None
            if LATEST_METRICS["tok_per_sec"] is None
            else round(float(LATEST_METRICS["tok_per_sec"]), 2)
        ),
        "ttft_ms": (
            None
            if LATEST_METRICS["ttft_ms"] is None
            else round(float(LATEST_METRICS["ttft_ms"]), 2)
        ),
        "model_loaded": model_loaded,
    }
