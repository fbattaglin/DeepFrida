from __future__ import annotations

import json
import os
import sys
import time
from uuid import uuid4

import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import StreamingResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import OLLAMA_BASE
from db import add_message, get_conversation, get_messages, update_conversation_timestamp
from ollama_client import is_model_loaded
from routes.metrics import set_latest_metrics

router = APIRouter(prefix="/chat", tags=["chat"])

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
TAG_PREFIXES = (THINK_OPEN, THINK_CLOSE)


class ChatOptions(BaseModel):
    temperature: float = 0.6
    top_p: float = 0.9
    num_ctx: int = 4096


class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    model: str
    system_prompt: str = ""
    options: ChatOptions = ChatOptions()


class ThinkStreamParser:
    def __init__(self) -> None:
        self.in_think = False
        self.tag_buffer = ""
        self.answer_parts: list[str] = []
        self.think_parts: list[str] = []

    def append_think(self, text: str) -> list[tuple[str, str]]:
        if not text:
            return []
        self.think_parts.append(text)
        return [("think", text)]

    def _append(self, content: str) -> tuple[str, str] | None:
        if not content:
            return None
        if self.in_think:
            self.think_parts.append(content)
            return ("think", content)
        self.answer_parts.append(content)
        return ("token", content)

    def _drain_non_tag_prefix(self) -> list[tuple[str, str]]:
        emitted: list[tuple[str, str]] = []
        while self.tag_buffer and not any(tag.startswith(self.tag_buffer) for tag in TAG_PREFIXES):
            result = self._append(self.tag_buffer[0])
            self.tag_buffer = self.tag_buffer[1:]
            if result:
                emitted.append(result)
        return emitted

    def feed(self, text: str) -> list[tuple[str, str]]:
        emitted: list[tuple[str, str]] = []
        for char in text:
            if self.tag_buffer or char == "<":
                self.tag_buffer += char
                if self.tag_buffer == THINK_OPEN:
                    self.in_think = True
                    self.tag_buffer = ""
                    continue
                if self.tag_buffer == THINK_CLOSE:
                    self.in_think = False
                    self.tag_buffer = ""
                    continue
                emitted.extend(self._drain_non_tag_prefix())
                continue

            result = self._append(char)
            if result:
                emitted.append(result)
        return emitted

    def flush(self) -> list[tuple[str, str]]:
        emitted: list[tuple[str, str]] = []
        if self.tag_buffer:
            result = self._append(self.tag_buffer)
            self.tag_buffer = ""
            if result:
                emitted.append(result)
        return emitted

    @property
    def answer(self) -> str:
        return "".join(self.answer_parts).strip()

    @property
    def think(self) -> str:
        return "".join(self.think_parts).strip()


def sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_history_payload(messages: list[dict], system_prompt: str) -> list[dict]:
    payload: list[dict] = []
    if system_prompt.strip():
        payload.append({"role": "system", "content": system_prompt})

    for message in messages:
        payload.append({"role": message["role"], "content": message["content"]})
    return payload


@router.post("")
async def chat_route(payload: ChatRequest) -> StreamingResponse:
    async def event_stream():
        conversation = await get_conversation(payload.conversation_id)
        if conversation is None:
            yield sse_event({"type": "error", "message": "Conversation not found"})
            return

        try:
            model_loaded = is_model_loaded(payload.model)
        except RuntimeError:
            yield sse_event({"type": "error", "message": "Ollama is not running"})
            return

        if not model_loaded:
            yield sse_event(
                {
                    "type": "error",
                    "message": f"Model '{payload.model}' is not loaded. Warm it up first.",
                }
            )
            return

        await add_message(
            message_id=str(uuid4()),
            conversation_id=payload.conversation_id,
            role="user",
            content=payload.message,
        )
        await update_conversation_timestamp(payload.conversation_id)

        history = await get_messages(payload.conversation_id)
        messages = build_history_payload(history, payload.system_prompt)

        parser = ThinkStreamParser()
        first_token_at: float | None = None
        started_at = time.perf_counter()
        total_tokens = 0

        request_payload = {
            "model": payload.model,
            "messages": messages,
            "stream": True,
            "options": payload.options.model_dump(),
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE}/api/chat",
                    json=request_payload,
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line:
                            continue

                        chunk = json.loads(line)
                        message = chunk.get("message", {})
                        think_token = message.get("thinking", "") or chunk.get("thinking", "")
                        token = message.get("content", "") or chunk.get("response", "")

                        if (think_token or token) and first_token_at is None:
                            first_token_at = time.perf_counter()

                        for event_type, content in parser.append_think(think_token):
                            yield sse_event({"type": event_type, "content": content})

                        for event_type, content in parser.feed(token):
                            yield sse_event({"type": event_type, "content": content})

                        if chunk.get("done"):
                            total_tokens = int(chunk.get("eval_count") or 0)
                            break
        except httpx.ConnectError:
            yield sse_event({"type": "error", "message": "Ollama is not running"})
            return
        except httpx.HTTPError as exc:
            yield sse_event({"type": "error", "message": f"Ollama request failed: {exc}"})
            return
        except Exception as exc:
            yield sse_event({"type": "error", "message": str(exc)})
            return

        for event_type, content in parser.flush():
            yield sse_event({"type": event_type, "content": content})

        completed_at = time.perf_counter()
        ttft_ms = ((first_token_at - started_at) * 1000) if first_token_at else None
        elapsed_s = completed_at - started_at
        tok_per_sec = (total_tokens / elapsed_s) if total_tokens and elapsed_s > 0 else None

        await add_message(
            message_id=str(uuid4()),
            conversation_id=payload.conversation_id,
            role="assistant",
            content=parser.answer,
            think_content=parser.think,
            ttft_ms=ttft_ms,
            tok_per_sec=tok_per_sec,
            total_tokens=total_tokens,
        )
        await update_conversation_timestamp(payload.conversation_id)
        set_latest_metrics(model=payload.model, tok_per_sec=tok_per_sec, ttft_ms=ttft_ms)

        if ttft_ms is not None or tok_per_sec is not None:
            yield sse_event(
                {
                    "type": "metrics",
                    "ttft_ms": round(ttft_ms or 0, 2),
                    "tok_per_sec": round(tok_per_sec or 0, 2),
                }
            )

        yield sse_event({"type": "done", "total_tokens": total_tokens})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
