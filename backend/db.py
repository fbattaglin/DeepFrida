from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from config import DB_PATH, DEFAULT_MODEL

DEFAULT_PRESETS = [
    ("Terse MLOps engineer", "Be direct. Use code. No filler."),
    ("Code reviewer", "Review for correctness, performance, clarity."),
    ("Explain to director", "No jargon. Focus on business impact."),
    ("R1 reasoning", "Think step by step. Show your work."),
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


async def _connect() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    # Overwrite deleted payload bytes before SQLite recycles the freed pages.
    await db.execute("PRAGMA secure_delete = ON")
    return db


def _row_to_dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


async def _reclaim_storage_space() -> None:
    db = await _connect()
    try:
        # Rebuild the DB file after destructive deletes so disk usage is returned
        # to the OS instead of only becoming reusable free pages inside SQLite.
        await db.execute("VACUUM")
    finally:
        await db.close()


async def init_db() -> None:
    db = await _connect()
    try:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                model TEXT NOT NULL,
                system_prompt TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                think_content TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                ttft_ms REAL,
                tok_per_sec REAL,
                total_tokens INTEGER
            );

            CREATE TABLE IF NOT EXISTS presets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        for name, content in DEFAULT_PRESETS:
            cursor = await db.execute(
                "SELECT id FROM presets WHERE name = ? AND content = ?",
                (name, content),
            )
            row = await cursor.fetchone()
            if row is None:
                from uuid import uuid4

                await db.execute(
                    """
                    INSERT INTO presets (id, name, content, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (str(uuid4()), name, content, utc_now()),
                )

        await db.commit()
    finally:
        await db.close()


async def get_conversations() -> list[dict[str, Any]]:
    db = await _connect()
    try:
        cursor = await db.execute(
            """
            SELECT
                c.*,
                COUNT(m.id) AS turn_count
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        conversation = _row_to_dict(await cursor.fetchone())
        if conversation is None:
            return None

        conversation["messages"] = await get_messages(conversation_id)
        return conversation
    finally:
        await db.close()


async def create_conversation(
    conversation_id: str,
    title: str,
    model: str = DEFAULT_MODEL,
    system_prompt: str = "",
) -> dict[str, Any]:
    timestamp = utc_now()
    db = await _connect()
    try:
        await db.execute(
            """
            INSERT INTO conversations (id, title, model, system_prompt, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, title, model, system_prompt, timestamp, timestamp),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "id": conversation_id,
        "title": title,
        "model": model,
        "system_prompt": system_prompt,
        "created_at": timestamp,
        "updated_at": timestamp,
        "turn_count": 0,
        "messages": [],
    }


async def update_conversation_title(conversation_id: str, title: str) -> dict[str, Any] | None:
    return await update_conversation(conversation_id, title=title)


async def update_conversation(
    conversation_id: str,
    title: str | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
) -> dict[str, Any] | None:
    current = await get_conversation(conversation_id)
    if current is None:
        return None

    next_title = title if title is not None else current["title"]
    next_prompt = system_prompt if system_prompt is not None else current["system_prompt"]
    next_model = model if model is not None else current["model"]
    updated_at = utc_now()

    db = await _connect()
    try:
        await db.execute(
            """
            UPDATE conversations
            SET title = ?, model = ?, system_prompt = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_title, next_model, next_prompt, updated_at, conversation_id),
        )
        await db.commit()
    finally:
        await db.close()

    return await get_conversation(conversation_id)


async def delete_conversation(conversation_id: str) -> bool:
    deleted = False
    db = await _connect()
    try:
        cursor = await db.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        await db.commit()
        deleted = cursor.rowcount > 0
    finally:
        await db.close()

    if deleted:
        # Space reclamation is best-effort; the user-facing delete should still
        # succeed even if SQLite cannot vacuum immediately.
        with suppress(aiosqlite.Error):
            await _reclaim_storage_space()

    return deleted


async def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    db = await _connect()
    try:
        cursor = await db.execute(
            """
            SELECT *
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def add_message(
    *,
    message_id: str,
    conversation_id: str,
    role: str,
    content: str,
    think_content: str = "",
    ttft_ms: float | None = None,
    tok_per_sec: float | None = None,
    total_tokens: int | None = None,
) -> dict[str, Any]:
    created_at = utc_now()
    db = await _connect()
    try:
        await db.execute(
            """
            INSERT INTO messages (
                id, conversation_id, role, content, think_content,
                created_at, ttft_ms, tok_per_sec, total_tokens
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation_id,
                role,
                content,
                think_content,
                created_at,
                ttft_ms,
                tok_per_sec,
                total_tokens,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "id": message_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "think_content": think_content,
        "created_at": created_at,
        "ttft_ms": ttft_ms,
        "tok_per_sec": tok_per_sec,
        "total_tokens": total_tokens,
    }


async def update_conversation_timestamp(conversation_id: str) -> None:
    db = await _connect()
    try:
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (utc_now(), conversation_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_presets() -> list[dict[str, Any]]:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT * FROM presets ORDER BY created_at ASC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def create_preset(preset_id: str, name: str, content: str) -> dict[str, Any]:
    created_at = utc_now()
    db = await _connect()
    try:
        await db.execute(
            """
            INSERT INTO presets (id, name, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (preset_id, name, content, created_at),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "id": preset_id,
        "name": name,
        "content": content,
        "created_at": created_at,
    }


async def delete_preset(preset_id: str) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute(
            "DELETE FROM presets WHERE id = ?",
            (preset_id,),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()
