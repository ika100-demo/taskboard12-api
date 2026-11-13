"""Unit tests for InMemoryTaskStore and per-app store wiring."""

from __future__ import annotations

from datetime import UTC, date
from threading import Thread

from taskboard12_api.main import create_app
from taskboard12_api.tasks import InMemoryTaskStore


def test_add_returns_task_with_id_and_utc_created_at() -> None:
    task = InMemoryTaskStore().add("write", date(2030, 1, 2))
    assert isinstance(task.id, str)
    assert task.id
    assert task.title == "write"
    assert task.due_date == date(2030, 1, 2)
    assert task.created_at.tzinfo is not None
    assert task.created_at.utcoffset() == UTC.utcoffset(None)


def test_add_generates_unique_ids() -> None:
    store = InMemoryTaskStore()
    assert store.add("a", None).id != store.add("b", None).id


def test_list_empty() -> None:
    assert InMemoryTaskStore().list() == []


def test_list_preserves_insertion_order() -> None:
    store = InMemoryTaskStore()
    for title in ("a", "b", "c"):
        store.add(title, None)
    assert [t.title for t in store.list()] == ["a", "b", "c"]


def test_list_returns_a_copy() -> None:
    store = InMemoryTaskStore()
    store.add("a", None)
    snapshot = store.list()
    snapshot.clear()
    assert len(store.list()) == 1
    store.add("b", None)
    assert len(snapshot) == 0


def test_concurrent_adds_lose_nothing() -> None:
    store = InMemoryTaskStore()

    def work() -> None:
        for i in range(100):
            store.add(f"t{i}", None)

    threads = [Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    tasks = store.list()
    assert len(tasks) == 800
    assert len({t.id for t in tasks}) == 800


def test_create_app_gives_each_app_its_own_store() -> None:
    app1, app2 = create_app(), create_app()
    assert isinstance(app1.state.task_store, InMemoryTaskStore)
    assert app1.state.task_store is not app2.state.task_store
    app1.state.task_store.add("only-in-1", None)
    assert app2.state.task_store.list() == []
