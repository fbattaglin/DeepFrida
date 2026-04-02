from __future__ import annotations

from asyncio import LifoQueue, Lock
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Any, AsyncIterator
from uuid import uuid4

import aiosqlite

from config import DB_PATH, DEFAULT_MODEL

DEFAULT_PRESETS = [
    ("Terse MLOps engineer", "Be direct. Use code. No filler."),
    ("Code reviewer", "Review for correctness, performance, clarity."),
    ("Explain to director", "No jargon. Focus on business impact."),
    ("R1 reasoning", "Think step by step. Show your work."),
]

POOL_SIZE = 6

SQLITE_PRAGMAS = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA temp_store = MEMORY;
PRAGMA cache_size = -32768;
PRAGMA mmap_size = 268435456;
PRAGMA wal_autocheckpoint = 1000;
PRAGMA secure_delete = ON;
"""

SCHEMA = """
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

CREATE TABLE IF NOT EXISTS inference_runs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    temperature REAL NOT NULL,
    top_p REAL NOT NULL,
    num_ctx INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    error TEXT DEFAULT '',
    ttft_ms REAL,
    tok_per_sec REAL,
    total_tokens INTEGER
);

CREATE INDEX IF NOT EXISTS idx_conversations_updated_at
    ON conversations(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created_at
    ON messages(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_inference_runs_conversation_started_at
    ON inference_runs(conversation_id, started_at DESC);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SQLitePool:
    def __init__(self, size: int = POOL_SIZE) -> None:
        self._size = size
        self._available: LifoQueue[aiosqlite.Connection] = LifoQueue(maxsize=size)
        self._opened = False

    async def open(self) -> None:
        if self._opened:
            return

        for _ in range(self._size):
            await self._available.put(await _create_connection())
        self._opened = True

    async def close(self) -> None:
        if not self._opened:
            return

        while not self._available.empty():
            connection = await self._available.get()
            await connection.close()

        self._opened = False

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        if not self._opened:
            raise RuntimeError("SQLite pool is not initialized")

        connection = await self._available.get()
        try:
            yield connection
        finally:
            await self._available.put(connection)


_pool: SQLitePool | None = None
_pool_lock = Lock()


async def _create_connection() -> aiosqlite.Connection:
    connection = await aiosqlite.connect(DB_PATH)
    connection.row_factory = aiosqlite.Row
    await connection.executescript(SQLITE_PRAGMAS)
    return connection


async def _ensure_pool() -> SQLitePool:
    global _pool

    if _pool is not None:
        return _pool

    async with _pool_lock:
        if _pool is None:
            _pool = SQLitePool()
            await _pool.open()
    return _pool


async def close_db() -> None:
    global _pool

    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
            _pool = None


@asynccontextmanager
async def _connection() -> AsyncIterator[aiosqlite.Connection]:
    pool = await _ensure_pool()
    async with pool.connection() as connection:
        yield connection


def _row_to_dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


async def _current_auto_vacuum_mode(connection: aiosqlite.Connection) -> int:
    cursor = await connection.execute("PRAGMA auto_vacuum")
    row = await cursor.fetchone()
    return int(row[0]) if row is not None else 0


async def _seed_default_presets(connection: aiosqlite.Connection) -> None:
    for name, content in DEFAULT_PRESETS:
        cursor = await connection.execute(
            "SELECT id FROM presets WHERE name = ? AND content = ?",
            (name, content),
        )
        row = await cursor.fetchone()
        if row is None:
            await connection.execute(
                """
                INSERT INTO presets (id, name, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (str(uuid4()), name, content, utc_now()),
            )


async def _fetch_messages(
    connection: aiosqlite.Connection,
    conversation_id: str,
) -> list[dict[str, Any]]:
    cursor = await connection.execute(
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


async def _fetch_conversation(
    connection: aiosqlite.Connection,
    conversation_id: str,
) -> dict[str, Any] | None:
    cursor = await connection.execute(
        """
        SELECT
            c.*,
            COUNT(m.id) AS turn_count
        FROM conversations c
        LEFT JOIN messages m ON m.conversation_id = c.id
        WHERE c.id = ?
        GROUP BY c.id
        """,
        (conversation_id,),
    )
    return _row_to_dict(await cursor.fetchone())


async def _incremental_vacuum(page_count: int = 128) -> None:
    async with _connection() as connection:
        await connection.execute(f"PRAGMA incremental_vacuum({page_count})")
        await connection.commit()


async def init_db() -> None:
    bootstrap = await _create_connection()
    try:
        auto_vacuum_mode = await _current_auto_vacuum_mode(bootstrap)
        if auto_vacuum_mode != 2:
            await bootstrap.execute("PRAGMA auto_vacuum = INCREMENTAL")

        await bootstrap.executescript(SCHEMA)
        await _seed_default_presets(bootstrap)
        await bootstrap.commit()

        if auto_vacuum_mode != 2:
            await bootstrap.execute("VACUUM")
    finally:
        await bootstrap.close()

    await _ensure_pool()


async def get_conversations() -> list[dict[str, Any]]:
    async with _connection() as connection:
        cursor = await connection.execute(
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


async def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    async with _connection() as connection:
        conversation = await _fetch_conversation(connection, conversation_id)
        if conversation is None:
            return None

        conversation["messages"] = await _fetch_messages(connection, conversation_id)
        return conversation


async def create_conversation(
    conversation_id: str,
    title: str,
    model: str = DEFAULT_MODEL,
    system_prompt: str = "",
) -> dict[str, Any]:
    timestamp = utc_now()

    async with _connection() as connection:
        await connection.execute(
            """
            INSERT INTO conversations (id, title, model, system_prompt, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, title, model, system_prompt, timestamp, timestamp),
        )
        await connection.commit()

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
    async with _connection() as connection:
        current = await _fetch_conversation(connection, conversation_id)
        if current is None:
            return None

        next_title = title if title is not None else current["title"]
        next_prompt = system_prompt if system_prompt is not None else current["system_prompt"]
        next_model = model if model is not None else current["model"]

        await connection.execute(
            """
            UPDATE conversations
            SET title = ?, model = ?, system_prompt = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_title, next_model, next_prompt, utc_now(), conversation_id),
        )
        await connection.commit()

        updated = await _fetch_conversation(connection, conversation_id)
        if updated is None:
            return None
        updated["messages"] = await _fetch_messages(connection, conversation_id)
        return updated


async def delete_conversation(conversation_id: str) -> bool:
    async with _connection() as connection:
        cursor = await connection.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        await connection.commit()
        deleted = cursor.rowcount > 0

    if deleted:
        # Reclaim a bounded amount of free pages without forcing a full VACUUM
        # on the hot request path.
        with suppress(aiosqlite.Error):
            await _incremental_vacuum()

    return deleted


async def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    async with _connection() as connection:
        return await _fetch_messages(connection, conversation_id)


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

    async with _connection() as connection:
        await connection.execute(
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
        await connection.commit()

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
    async with _connection() as connection:
        await connection.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (utc_now(), conversation_id),
        )
        await connection.commit()


async def create_inference_run(
    *,
    run_id: str,
    conversation_id: str,
    model: str,
    temperature: float,
    top_p: float,
    num_ctx: int,
) -> dict[str, Any]:
    started_at = utc_now()

    async with _connection() as connection:
        await connection.execute(
            """
            INSERT INTO inference_runs (
                id, conversation_id, model, temperature, top_p, num_ctx,
                started_at, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, conversation_id, model, temperature, top_p, num_ctx, started_at, "running"),
        )
        await connection.commit()

    return {
        "id": run_id,
        "conversation_id": conversation_id,
        "model": model,
        "temperature": temperature,
        "top_p": top_p,
        "num_ctx": num_ctx,
        "started_at": started_at,
        "status": "running",
    }


async def finalize_inference_run(
    run_id: str,
    *,
    status: str,
    error: str | None = None,
    ttft_ms: float | None = None,
    tok_per_sec: float | None = None,
    total_tokens: int | None = None,
) -> None:
    async with _connection() as connection:
        await connection.execute(
            """
            UPDATE inference_runs
            SET completed_at = ?, status = ?, error = ?, ttft_ms = ?, tok_per_sec = ?, total_tokens = ?
            WHERE id = ?
            """,
            (
                utc_now(),
                status,
                error or "",
                ttft_ms,
                tok_per_sec,
                total_tokens,
                run_id,
            ),
        )
        await connection.commit()


async def get_presets() -> list[dict[str, Any]]:
    async with _connection() as connection:
        cursor = await connection.execute("SELECT * FROM presets ORDER BY created_at ASC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def create_preset(preset_id: str, name: str, content: str) -> dict[str, Any]:
    created_at = utc_now()

    async with _connection() as connection:
        await connection.execute(
            """
            INSERT INTO presets (id, name, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (preset_id, name, content, created_at),
        )
        await connection.commit()

    return {
        "id": preset_id,
        "name": name,
        "content": content,
        "created_at": created_at,
    }


async def delete_preset(preset_id: str) -> bool:
    async with _connection() as connection:
        cursor = await connection.execute(
            "DELETE FROM presets WHERE id = ?",
            (preset_id,),
        )
        await connection.commit()
        return cursor.rowcount > 0
