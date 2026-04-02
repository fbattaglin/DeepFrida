from __future__ import annotations

import json
import os
import sys
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import GLOBAL_SYSTEM_PROMPT
from db import (
    add_message,
    create_inference_run,
    finalize_inference_run,
    get_conversation,
    get_messages,
    update_conversation_timestamp,
)
from routes.metrics import set_latest_metrics
from services.observability import log_inference_event
from services.ollama_async import (
    OllamaResponseError,
    OllamaUnavailableError,
    get_ollama_client,
)
from services.stream_parser import ThinkStreamParser

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = 0.6
    top_p: float = 0.9
    num_ctx: int = 4096


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    message: str
    model: str
    system_prompt: str = ""
    options: ChatOptions = Field(default_factory=ChatOptions)


class ClientDisconnected(RuntimeError):
    pass


def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def compose_system_prompt(conversation_prompt: str) -> str:
    sections = [GLOBAL_SYSTEM_PROMPT.strip()]
    if conversation_prompt.strip():
        sections.append(f"Conversation-specific instructions:\n{conversation_prompt.strip()}")
    return "\n\n".join(sections)


def build_history_payload(
    messages: list[dict[str, Any]],
    system_prompt: str,
    prompt_revision: int,
) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    effective_system_prompt = compose_system_prompt(system_prompt)
    if effective_system_prompt:
        payload.append({"role": "system", "content": effective_system_prompt})

    current_scope_messages = [
        message for message in messages if int(message.get("prompt_revision", 0)) == prompt_revision
    ]
    payload.extend(
        {"role": message["role"], "content": message["content"]} for message in current_scope_messages
    )
    return payload


def build_request_payload(
    payload: ChatRequest,
    messages: list[dict[str, Any]],
    prompt_revision: int,
) -> dict[str, Any]:
    return {
        "model": payload.model,
        "messages": build_history_payload(messages, payload.system_prompt, prompt_revision),
        "stream": True,
        "options": payload.options.model_dump(),
    }


def prompt_preview(value: str, limit: int = 96) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


@router.post("")
async def chat_route(payload: ChatRequest, request: Request) -> StreamingResponse:
    async def event_stream():
        run_id = str(uuid4())
        started_at = time.perf_counter()
        first_token_at: float | None = None
        total_tokens = 0
        assistant_persisted = False
        parser = ThinkStreamParser()

        conversation = await get_conversation(payload.conversation_id)
        if conversation is None:
            yield sse_event({"type": "error", "message": "Conversation not found"})
            return

        options = payload.options.model_dump()
        prompt_revision = int(conversation.get("prompt_revision", 0))
        effective_system_prompt = compose_system_prompt(payload.system_prompt)
        conversation_prompt_preview = prompt_preview(payload.system_prompt)
        effective_prompt_preview = prompt_preview(effective_system_prompt)
        await create_inference_run(
            run_id=run_id,
            conversation_id=payload.conversation_id,
            model=payload.model,
            temperature=payload.options.temperature,
            top_p=payload.options.top_p,
            num_ctx=payload.options.num_ctx,
        )
        log_inference_event(
            "inference_started",
            run_id=run_id,
            conversation_id=payload.conversation_id,
            model=payload.model,
            options=options,
            system_prompt_length=len(payload.system_prompt),
            system_prompt_preview=conversation_prompt_preview,
            effective_system_prompt_length=len(effective_system_prompt),
            effective_system_prompt_preview=effective_prompt_preview,
        )

        try:
            model_loaded = await get_ollama_client().is_model_loaded(payload.model)
        except (OllamaUnavailableError, OllamaResponseError) as exc:
            await finalize_inference_run(run_id, status="failed", error=str(exc))
            log_inference_event(
                "inference_failed",
                run_id=run_id,
                conversation_id=payload.conversation_id,
                model=payload.model,
                error=str(exc),
                system_prompt_preview=conversation_prompt_preview,
                effective_system_prompt_preview=effective_prompt_preview,
            )
            yield sse_event({"type": "error", "message": "Ollama is not running"})
            return

        if not model_loaded:
            message = f"Model '{payload.model}' is not loaded. Warm it up first."
            await finalize_inference_run(run_id, status="failed", error=message)
            log_inference_event(
                "inference_failed",
                run_id=run_id,
                conversation_id=payload.conversation_id,
                model=payload.model,
                error=message,
                system_prompt_preview=conversation_prompt_preview,
                effective_system_prompt_preview=effective_prompt_preview,
            )
            yield sse_event({"type": "error", "message": message})
            return

        await add_message(
            message_id=str(uuid4()),
            conversation_id=payload.conversation_id,
            role="user",
            content=payload.message,
            prompt_revision=prompt_revision,
        )
        await update_conversation_timestamp(payload.conversation_id)

        history = await get_messages(payload.conversation_id)
        request_payload = build_request_payload(payload, history, prompt_revision)

        try:
            async for chunk in get_ollama_client().stream_chat(request_payload):
                if await request.is_disconnected():
                    raise ClientDisconnected()

                message = chunk.get("message", {})
                think_token = message.get("thinking", "") or chunk.get("thinking", "")
                answer_token = message.get("content", "") or chunk.get("response", "")

                if (think_token or answer_token) and first_token_at is None:
                    first_token_at = time.perf_counter()

                for fragment in parser.feed_thinking(think_token):
                    yield sse_event({"type": fragment.kind, "content": fragment.content})

                for fragment in parser.feed_content(answer_token):
                    yield sse_event({"type": fragment.kind, "content": fragment.content})

                if chunk.get("done"):
                    total_tokens = int(chunk.get("eval_count") or 0)
                    break
        except ClientDisconnected:
            ttft_ms = ((first_token_at - started_at) * 1000) if first_token_at else None
            await finalize_inference_run(
                run_id,
                status="cancelled",
                error="client_disconnected",
                ttft_ms=ttft_ms,
            )
            log_inference_event(
                "inference_cancelled",
                run_id=run_id,
                conversation_id=payload.conversation_id,
                model=payload.model,
                ttft_ms=ttft_ms,
                system_prompt_preview=conversation_prompt_preview,
                effective_system_prompt_preview=effective_prompt_preview,
            )
            return
        except OllamaUnavailableError as exc:
            await finalize_inference_run(run_id, status="failed", error=str(exc))
            log_inference_event(
                "inference_failed",
                run_id=run_id,
                conversation_id=payload.conversation_id,
                model=payload.model,
                error=str(exc),
                system_prompt_preview=conversation_prompt_preview,
                effective_system_prompt_preview=effective_prompt_preview,
            )
            yield sse_event({"type": "error", "message": "Ollama is not running"})
            return
        except OllamaResponseError as exc:
            await finalize_inference_run(run_id, status="failed", error=str(exc))
            log_inference_event(
                "inference_failed",
                run_id=run_id,
                conversation_id=payload.conversation_id,
                model=payload.model,
                error=str(exc),
                system_prompt_preview=conversation_prompt_preview,
                effective_system_prompt_preview=effective_prompt_preview,
            )
            yield sse_event({"type": "error", "message": f"Ollama request failed: {exc}"})
            return
        except Exception as exc:
            await finalize_inference_run(run_id, status="failed", error=str(exc))
            log_inference_event(
                "inference_failed",
                run_id=run_id,
                conversation_id=payload.conversation_id,
                model=payload.model,
                error=str(exc),
                system_prompt_preview=conversation_prompt_preview,
                effective_system_prompt_preview=effective_prompt_preview,
            )
            yield sse_event({"type": "error", "message": str(exc)})
            return

        for fragment in parser.flush():
            yield sse_event({"type": fragment.kind, "content": fragment.content})

        completed_at = time.perf_counter()
        ttft_ms = ((first_token_at - started_at) * 1000) if first_token_at else None
        decode_window_s = completed_at - (first_token_at or started_at)
        tok_per_sec = (total_tokens / decode_window_s) if total_tokens and decode_window_s > 0 else None

        if parser.answer or parser.think:
            await add_message(
                message_id=str(uuid4()),
                conversation_id=payload.conversation_id,
                role="assistant",
                content=parser.answer,
                think_content=parser.think,
                prompt_revision=prompt_revision,
                ttft_ms=ttft_ms,
                tok_per_sec=tok_per_sec,
                total_tokens=total_tokens,
            )
            assistant_persisted = True
            await update_conversation_timestamp(payload.conversation_id)

        await finalize_inference_run(
            run_id,
            status="completed",
            ttft_ms=ttft_ms,
            tok_per_sec=tok_per_sec,
            total_tokens=total_tokens,
        )
        set_latest_metrics(model=payload.model, tok_per_sec=tok_per_sec, ttft_ms=ttft_ms)
        log_inference_event(
            "inference_completed",
            run_id=run_id,
            conversation_id=payload.conversation_id,
            model=payload.model,
            ttft_ms=ttft_ms,
            tok_per_sec=tok_per_sec,
            total_tokens=total_tokens,
            assistant_persisted=assistant_persisted,
            system_prompt_preview=conversation_prompt_preview,
            effective_system_prompt_preview=effective_prompt_preview,
        )

        if ttft_ms is not None or tok_per_sec is not None:
            yield sse_event(
                {
                    "type": "metrics",
                    "ttft_ms": round(ttft_ms or 0, 2),
                    "tok_per_sec": round(tok_per_sec or 0, 2),
                }
            )

        yield sse_event({"type": "done", "total_tokens": total_tokens})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
