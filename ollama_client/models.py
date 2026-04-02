import time

import requests

from .config import OLLAMA_BASE

_CONN_ERR = f"Cannot reach Ollama at {OLLAMA_BASE}. Is it running?"


def list_models() -> list:
    """Return all downloaded models."""
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=10)
        resp.raise_for_status()
        return resp.json().get("models", [])
    except requests.exceptions.ConnectionError:
        raise RuntimeError(_CONN_ERR)
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama did not respond in time (list_models).")


def is_model_loaded(model: str) -> bool:
    """True if the model is currently resident in unified memory."""
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/ps", timeout=5)
        resp.raise_for_status()
        running = resp.json().get("models", [])
        return any(m["name"].startswith(model.split(":")[0]) for m in running)
    except requests.exceptions.ConnectionError:
        raise RuntimeError(_CONN_ERR)
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama did not respond in time (is_model_loaded).")


def model_info(model: str) -> dict:
    """Return architecture metadata for a model."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/show",
            json={"name": model},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(_CONN_ERR)
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama did not respond in time (model_info: {model}).")


def warmup(model: str) -> float:
    """Force model into unified memory. Returns load time in seconds."""
    t = time.perf_counter()
    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": model, "prompt": " ", "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(_CONN_ERR)
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama warmup timed out for model '{model}'.")
    return round(time.perf_counter() - t, 2)
