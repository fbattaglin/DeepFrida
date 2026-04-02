from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.responses import JSONResponse

from config import OLLAMA_BASE
from ollama_client import warmup

router = APIRouter(prefix="/models", tags=["models"])


class WarmupRequest(BaseModel):
    model: str


def _offline_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": "Ollama is not running"},
    )


async def _proxy_json(path: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{OLLAMA_BASE}{path}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Ollama is not running") from exc


@router.get("")
async def list_models_route() -> dict:
    try:
        return await _proxy_json("/api/tags")
    except HTTPException:
        return _offline_response()


@router.get("/loaded")
async def loaded_models_route() -> dict:
    try:
        return await _proxy_json("/api/ps")
    except HTTPException:
        return _offline_response()


@router.post("/warmup")
async def warmup_model_route(payload: WarmupRequest) -> dict:
    try:
        load_time_s = warmup(payload.model)
    except RuntimeError:
        return _offline_response()
    return {"load_time_s": load_time_s}
