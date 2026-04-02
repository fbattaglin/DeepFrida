from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import create_preset, delete_preset, get_presets

router = APIRouter(prefix="/presets", tags=["presets"])


class PresetCreate(BaseModel):
    name: str
    content: str


@router.get("")
async def list_presets_route() -> list[dict]:
    return await get_presets()


@router.post("", status_code=201)
async def create_preset_route(payload: PresetCreate) -> dict:
    return await create_preset(
        preset_id=str(uuid4()),
        name=payload.name,
        content=payload.content,
    )


@router.delete("/{preset_id}", status_code=204)
async def delete_preset_route(preset_id: str) -> None:
    deleted = await delete_preset(preset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Preset not found")
