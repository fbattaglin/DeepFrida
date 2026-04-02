from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from config import OLLAMA_BASE


class OllamaUnavailableError(RuntimeError):
    pass


class OllamaResponseError(RuntimeError):
    pass


class OllamaAsyncClient:
    def __init__(self, base_url: str = OLLAMA_BASE) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=5.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as exc:
            raise OllamaUnavailableError("Ollama is not running") from exc
        except httpx.HTTPError as exc:
            raise OllamaResponseError(str(exc)) from exc

    async def health(self) -> bool:
        try:
            await self._request_json("GET", "/api/tags")
            return True
        except (OllamaUnavailableError, OllamaResponseError):
            return False

    async def list_models(self) -> dict[str, Any]:
        return await self._request_json("GET", "/api/tags")

    async def loaded_models(self) -> dict[str, Any]:
        return await self._request_json("GET", "/api/ps")

    async def is_model_loaded(self, model: str) -> bool:
        payload = await self.loaded_models()
        running = payload.get("models", [])
        requested = model.strip()
        requested_base = requested.split(":", 1)[0]

        for entry in running:
            candidates = {
                str(entry.get("name") or "").strip(),
                str(entry.get("model") or "").strip(),
            }
            candidates.discard("")
            if requested in candidates:
                return True

            if ":" not in requested and any(candidate.split(":", 1)[0] == requested_base for candidate in candidates):
                return True

        return False

    async def warmup(self, model: str) -> float:
        started_at = time.perf_counter()
        await self._request_json(
            "POST",
            "/api/generate",
            json={"model": model, "prompt": " ", "stream": False},
        )
        return round(time.perf_counter() - started_at, 2)

    async def stream_chat(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    yield json.loads(line)
        except httpx.ConnectError as exc:
            raise OllamaUnavailableError("Ollama is not running") from exc
        except httpx.HTTPError as exc:
            raise OllamaResponseError(str(exc)) from exc


_client: OllamaAsyncClient | None = None


async def init_ollama_client() -> None:
    global _client
    if _client is None:
        _client = OllamaAsyncClient()


def get_ollama_client() -> OllamaAsyncClient:
    if _client is None:
        raise RuntimeError("Ollama client is not initialized")
    return _client


async def close_ollama_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
