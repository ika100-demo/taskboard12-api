"""Unit tests for PostgresTaskStore."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, date

import psycopg
import pytest

from taskboard12_api.tasks.store import PostgresTaskStore, StorageUnavailableError


async def test_add_and_list_in_creation_order(db_url: str) -> None:
    store = PostgresTaskStore(db_url)
    added = [await store.add(t, None) for t in ("a", "b", "c")]
    listed = await store.list()
    assert [t.title for t in listed] == ["a", "b", "c"]
    assert listed == added
    assert listed[0].created_at.tzinfo is not None
    assert listed[0].created_at.utcoffset() == UTC.utcoffset(None)


async def test_list_empty_creates_table(db_url: str) -> None:
    assert await PostgresTaskStore(db_url).list() == []


async def test_due_date_roundtrip(db_url: str) -> None:
    task = await PostgresTaskStore(db_url).add("x", date(2030, 1, 2))
    assert task.due_date == date(2030, 1, 2)


async def test_equal_created_at_ordered_by_seq(db_url: str) -> None:
    store = PostgresTaskStore(db_url)
    await store.ensure_schema()
    with psycopg.connect(db_url, autocommit=True) as conn:
        for i, uid in enumerate(
            ["00000000-0000-0000-0000-00000000000f", "00000000-0000-0000-0000-000000000001"]
        ):
            conn.execute(
                "INSERT INTO tasks (id, title, created_at) VALUES (%s, %s, '2030-01-01Z')",
                (uid, f"t{i}"),
            )
    assert [t.title for t in await store.list()] == ["t0", "t1"]


async def test_ensure_schema_is_idempotent(db_url: str) -> None:
    store = PostgresTaskStore(db_url)
    await store.ensure_schema()
    await store.add("keep", None)
    await store.ensure_schema()
    await asyncio.gather(PostgresTaskStore(db_url).ensure_schema(), store.ensure_schema())
    assert [t.title for t in await store.list()] == ["keep"]


async def test_ping_true_when_reachable(db_url: str) -> None:
    assert await PostgresTaskStore(db_url).ping() is True


async def test_closed_port_raises_and_ping_false(closed_port_url: str) -> None:
    store = PostgresTaskStore(closed_port_url)
    start = time.monotonic()
    with pytest.raises(StorageUnavailableError):
        await store.list()
    with pytest.raises(StorageUnavailableError):
        await store.add("x", None)
    assert await store.ping() is False
    assert time.monotonic() - start < 5


async def test_none_url() -> None:
    store = PostgresTaskStore(None)
    with pytest.raises(StorageUnavailableError):
        await store.list()
    with pytest.raises(StorageUnavailableError):
        await store.add("x", None)
    with pytest.raises(StorageUnavailableError):
        await store.ensure_schema()
    assert await store.ping() is False


async def test_error_does_not_leak_url(closed_port_url: str) -> None:
    with pytest.raises(StorageUnavailableError) as info:
        await PostgresTaskStore(closed_port_url).list()
    assert "u:p" not in str(info.value)
