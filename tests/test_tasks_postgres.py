"""Acceptance tests for spec 002 (tasks kept in Postgres, 503 while it is unreachable)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from taskboard12_api.main import create_app

UNAVAILABLE = {"detail": "Task storage is unavailable"}


def _restart(url: str) -> TestClient:
    """A new app on the same database: a new process as far as the store can tell."""
    return TestClient(create_app(database_url=url))


def test_tasks_survive_restart_in_creation_order(db_url: str) -> None:  # AC-002.1
    first = _restart(db_url)
    created = [
        first.post("/tasks", json={"title": title, "due_date": due})
        for title, due in [("A", "2026-12-01"), ("B", None), ("C", "2027-01-02")]
    ]
    assert [r.status_code for r in created] == [201, 201, 201]
    expected = [r.json() for r in created]

    second = _restart(db_url)
    response = second.get("/tasks")
    assert response.status_code == 200
    assert response.json() == expected
    assert [t["title"] for t in response.json()] == ["A", "B", "C"]


def test_many_quick_tasks_keep_creation_order_after_restart(db_url: str) -> None:  # AC-002.1
    first = _restart(db_url)
    titles = [f"t{i:02d}" for i in range(20)]
    for title in titles:
        assert first.post("/tasks", json={"title": title}).status_code == 201
    listed = _restart(db_url).get("/tasks").json()
    assert [t["title"] for t in listed] == titles


def test_empty_database_without_tables_lists_empty_then_accepts_task(
    db_url: str,
) -> None:  # AC-002.2
    client = _restart(db_url)  # the fixture dropped the table: no tables at all
    response = client.get("/tasks")
    assert response.status_code == 200
    assert response.json() == []

    created = client.post("/tasks", json={"title": "Buy milk", "due_date": "2026-12-01"})
    assert created.status_code == 201
    listed = client.get("/tasks")
    assert listed.status_code == 200
    assert listed.json() == [created.json()]


def test_post_first_on_database_without_tables(db_url: str) -> None:  # AC-002.2
    client = _restart(db_url)
    created = client.post("/tasks", json={"title": "Buy milk", "due_date": "2026-12-01"})
    assert created.status_code == 201
    assert client.get("/tasks").json() == [created.json()]


def test_stored_values_are_normalised_and_unchanged_after_restart(
    db_url: str,
) -> None:  # AC-002.3
    title = "x" * 200
    client = _restart(db_url)
    with_due = client.post("/tasks", json={"title": f"  {title}\n", "due_date": "2026-12-01"})
    without_due = client.post("/tasks", json={"title": f" \t{title} "})
    assert with_due.status_code == 201
    assert without_due.status_code == 201

    for listing in (client.get("/tasks").json(), _restart(db_url).get("/tasks").json()):
        assert listing == [with_due.json(), without_due.json()]
        assert [t["title"] for t in listing] == [title, title]
        assert [t["due_date"] for t in listing] == ["2026-12-01", None]
        for task in listing:
            parsed = datetime.fromisoformat(task["created_at"])
            assert parsed.utcoffset() == timedelta(0)


def test_get_tasks_is_503_when_database_refuses(closed_port_url: str) -> None:  # AC-002.4
    client = TestClient(create_app(database_url=closed_port_url))
    started = time.monotonic()
    response = client.get("/tasks")
    assert time.monotonic() - started < 5
    assert response.status_code == 503
    assert response.json() == UNAVAILABLE
    assert response.headers["content-type"].startswith("application/json")


def test_get_tasks_is_503_within_5s_through_closed_proxy(db_proxy: Any) -> None:  # AC-002.4
    client = TestClient(create_app(database_url=db_proxy.url))
    db_proxy.close()
    started = time.monotonic()
    response = client.get("/tasks")
    assert time.monotonic() - started < 5
    assert response.status_code == 503
    assert response.json() == UNAVAILABLE


def test_get_tasks_is_503_within_5s_when_database_hangs(db_proxy: Any) -> None:  # AC-002.4
    client = TestClient(create_app(database_url=db_proxy.url))
    db_proxy.hang()
    started = time.monotonic()
    response = client.get("/tasks")
    assert time.monotonic() - started < 5
    assert response.status_code == 503
    assert response.json() == UNAVAILABLE


def test_get_tasks_is_503_when_database_url_is_unset(
    monkeypatch: Any,
) -> None:  # AC-002.4
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app())
    response = client.get("/tasks")
    assert response.status_code == 503
    assert response.json() == UNAVAILABLE


def test_post_is_503_and_creates_nothing_while_database_is_down(
    db_proxy: Any, db_url: str
) -> None:  # AC-002.5
    client = TestClient(create_app(database_url=db_proxy.url))
    assert client.get("/tasks").json() == []  # schema exists, outage starts afterwards
    db_proxy.close()

    started = time.monotonic()
    response = client.post("/tasks", json={"title": "lost", "due_date": "2026-12-01"})
    assert time.monotonic() - started < 5
    assert response.status_code == 503
    assert response.json() == UNAVAILABLE

    db_proxy.open()
    listed = client.get("/tasks")
    assert listed.status_code == 200
    assert listed.json() == []
    assert _restart(db_url).get("/tasks").json() == []


def test_invalid_post_is_422_while_database_is_down(db_proxy: Any) -> None:  # AC-002.5
    client = TestClient(create_app(database_url=db_proxy.url))
    db_proxy.close()
    for payload in ({}, {"title": "   "}, {"title": "x" * 201}):
        response = client.post("/tasks", json=payload)
        assert response.status_code == 422
        assert ["body", "title"] in [e["loc"] for e in response.json()["detail"]]
    response = client.post("/tasks", json={"title": "ok", "due_date": "2026-02-30"})
    assert response.status_code == 422
    assert ["body", "due_date"] in [e["loc"] for e in response.json()["detail"]]


def test_ready_is_503_while_down_and_health_stays_200(db_proxy: Any) -> None:  # AC-002.6
    client = TestClient(create_app(database_url=db_proxy.url))
    assert client.get("/ready").status_code == 200
    db_proxy.close()

    ready = client.get("/ready")
    assert ready.status_code == 503
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}


def test_recovery_without_restart(db_proxy: Any) -> None:  # AC-002.6
    client = TestClient(create_app(database_url=db_proxy.url))
    db_proxy.close()
    assert client.get("/ready").status_code == 503
    assert client.get("/tasks").status_code == 503

    db_proxy.open()
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    tasks = client.get("/tasks")
    assert tasks.status_code == 200
    assert tasks.json() == []


def test_down_at_startup_does_not_crash_and_recovers(db_proxy: Any) -> None:  # AC-002.6
    db_proxy.close()
    with TestClient(create_app(database_url=db_proxy.url)) as client:  # runs the lifespan
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        db_proxy.open()
        assert client.get("/ready").status_code == 200
        created = client.post("/tasks", json={"title": "after outage"})
        assert created.status_code == 201
        assert client.get("/tasks").json() == [created.json()]
