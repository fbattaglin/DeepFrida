from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import DEFAULT_MODEL
from db import (
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversations,
    update_conversation,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    model: str = DEFAULT_MODEL
    title: str = "New conversation"
    system_prompt: str = ""


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None)
    system_prompt: str | None = Field(default=None)
    model: str | None = Field(default=None)


@router.get("")
async def list_conversations() -> list[dict]:
    return await get_conversations()


@router.post("", status_code=201)
async def create_conversation_route(payload: ConversationCreate) -> dict:
    return await create_conversation(
        conversation_id=str(uuid4()),
        title=payload.title,
        model=payload.model,
        system_prompt=payload.system_prompt,
    )


@router.get("/{conversation_id}")
async def get_conversation_route(conversation_id: str) -> dict:
    conversation = await get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.patch("/{conversation_id}")
async def update_conversation_route(conversation_id: str, payload: ConversationPatch) -> dict:
    if payload.title is None and payload.system_prompt is None and payload.model is None:
        raise HTTPException(status_code=400, detail="No fields provided")

    conversation = await update_conversation(
        conversation_id,
        title=payload.title,
        system_prompt=payload.system_prompt,
        model=payload.model,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation_route(conversation_id: str) -> None:
    deleted = await delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
