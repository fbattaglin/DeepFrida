from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import OLLAMA_BASE
from db import init_db
from routes.chat import router as chat_router
from routes.conversations import router as conversations_router
from routes.metrics import router as metrics_router
from routes.models import router as models_router
from routes.presets import router as presets_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="DeepFrida API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(conversations_router, prefix="/api")
app.include_router(models_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")
app.include_router(presets_router, prefix="/api")
app.include_router(chat_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    ollama = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE}/api/tags")
            ollama = response.status_code == 200
    except httpx.HTTPError:
        ollama = False

    return {"status": "ok", "ollama": ollama}
