"""Postgres-backed task store."""

from __future__ import annotations

import asyncio
import builtins
from datetime import UTC, date, datetime
from typing import cast
from uuid import uuid4

import psycopg
import structlog

from .models import Task

logger = structlog.get_logger(__name__)

_SCHEMA_LOCK_ID = 7_002_001
_CONNECT_TIMEOUT_S = 3
_CALL_TIMEOUT_S = 4.5
_CONNECT_OPTIONS = "-c statement_timeout=2000 -c TimeZone=UTC"

_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    seq        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id         uuid        NOT NULL UNIQUE,
    title      text        NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    due_date   date        NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
)
"""
_INSERT = (
    "INSERT INTO tasks (id, title, due_date) VALUES (%s, %s, %s) "
    "RETURNING id, title, due_date, created_at"
)
_SELECT = "SELECT id, title, due_date, created_at FROM tasks ORDER BY created_at, seq"

_STORAGE_ERRORS = (psycopg.Error, OSError, TimeoutError)

_Conn = psycopg.AsyncConnection[tuple[object, ...]]


class StorageUnavailableError(Exception):
    """The task storage could not be reached or failed."""


class PostgresTaskStore:
    def __init__(self, database_url: str | None) -> None:
        self._database_url = database_url
        self._schema_ready = False

    async def _connect(self) -> _Conn:
        if self._database_url is None:
            raise StorageUnavailableError("DATABASE_URL is not set")
        return await psycopg.AsyncConnection.connect(
            self._database_url,
            connect_timeout=_CONNECT_TIMEOUT_S,
            options=_CONNECT_OPTIONS,
        )

    @staticmethod
    async def _create_schema(conn: _Conn) -> None:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK_ID,))
            await conn.execute(_DDL)

    @staticmethod
    def _fail(exc: BaseException) -> StorageUnavailableError:
        logger.warning("task_storage_unavailable", error=type(exc).__name__)
        return StorageUnavailableError("Task storage is unavailable")

    async def ensure_schema(self) -> None:
        try:
            async with asyncio.timeout(_CALL_TIMEOUT_S):
                conn = await self._connect()
                async with conn:
                    await self._create_schema(conn)
            self._schema_ready = True
        except StorageUnavailableError:
            raise
        except _STORAGE_ERRORS as exc:
            raise self._fail(exc) from exc

    async def add(self, title: str, due_date: date | None) -> Task:
        try:
            async with asyncio.timeout(_CALL_TIMEOUT_S):
                conn = await self._connect()
                async with conn:
                    if not self._schema_ready:
                        await self._create_schema(conn)
                        self._schema_ready = True
                    cur = await conn.execute(_INSERT, (uuid4(), title, due_date))
                    row = await cur.fetchone()
        except StorageUnavailableError:
            raise
        except _STORAGE_ERRORS as exc:
            raise self._fail(exc) from exc
        if row is None:
            raise self._fail(RuntimeError("insert returned no row"))
        return _to_task(row)

    async def list(self) -> builtins.list[Task]:
        try:
            async with asyncio.timeout(_CALL_TIMEOUT_S):
                conn = await self._connect()
                async with conn:
                    if not self._schema_ready:
                        await self._create_schema(conn)
                        self._schema_ready = True
                    cur = await conn.execute(_SELECT)
                    rows = await cur.fetchall()
        except StorageUnavailableError:
            raise
        except _STORAGE_ERRORS as exc:
            raise self._fail(exc) from exc
        return [_to_task(row) for row in rows]

    async def ping(self, timeout: float = 0.8) -> bool:
        if self._database_url is None:
            return False
        try:
            async with asyncio.timeout(timeout):
                conn = await self._connect()
                async with conn:
                    await conn.execute("SELECT 1")
        except (*_STORAGE_ERRORS, StorageUnavailableError):
            return False
        return True


def _to_task(row: tuple[object, ...]) -> Task:
    task_id, title, due_date, created_at = row
    return Task(
        id=str(task_id),
        title=cast(str, title),
        due_date=cast("date | None", due_date),
        created_at=cast(datetime, created_at).astimezone(UTC),
    )
