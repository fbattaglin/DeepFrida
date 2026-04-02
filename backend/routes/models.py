from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from starlette.responses import JSONResponse
from services.ollama_async import (
    OllamaResponseError,
    OllamaUnavailableError,
    get_ollama_client,
)

router = APIRouter(prefix="/models", tags=["models"])


class WarmupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str


def _offline_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": "Ollama is not running"},
    )


@router.get("")
async def list_models_route() -> dict:
    try:
        return await get_ollama_client().list_models()
    except (OllamaUnavailableError, OllamaResponseError):
        return _offline_response()


@router.get("/loaded")
async def loaded_models_route() -> dict:
    try:
        return await get_ollama_client().loaded_models()
    except (OllamaUnavailableError, OllamaResponseError):
        return _offline_response()


@router.post("/warmup")
async def warmup_model_route(payload: WarmupRequest) -> dict:
    try:
        load_time_s = await get_ollama_client().warmup(payload.model)
    except (OllamaUnavailableError, OllamaResponseError):
        return _offline_response()
    return {"load_time_s": load_time_s}
