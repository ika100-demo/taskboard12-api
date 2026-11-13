"""Acceptance tests for spec 001 (create and list tasks in memory)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from taskboard12_api import main


@pytest.fixture()
def tasks_client(db_url: str) -> TestClient:
    # create_app is resolved at call time so a missing symbol fails each test on its own.
    return TestClient(main.create_app(database_url=db_url))  # type: ignore[attr-defined]


def _locs(response: Any) -> list[list[Any]]:
    return [entry["loc"] for entry in response.json()["detail"]]


def _assert_utc_timestamp(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    assert parsed.utcoffset() == timedelta(0)


def test_create_task_returns_201_with_task_object(tasks_client: TestClient) -> None:  # AC-001.1
    response = tasks_client.post("/tasks", json={"title": "Buy milk", "due_date": "2026-12-01"})
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], str) and body["id"]
    assert body["title"] == "Buy milk"
    assert body["due_date"] == "2026-12-01"
    _assert_utc_timestamp(body["created_at"])


def test_create_task_without_due_date_gives_null(tasks_client: TestClient) -> None:  # AC-001.2
    response = tasks_client.post("/tasks", json={"title": "Call Anna"})
    assert response.status_code == 201
    body = response.json()
    assert "due_date" in body
    assert body["due_date"] is None
    assert body["title"] == "Call Anna"


def test_list_tasks_in_creation_order(tasks_client: TestClient) -> None:  # AC-001.3
    created = [
        tasks_client.post("/tasks", json={"title": title, "due_date": due}).json()
        for title, due in [("A", "2026-12-01"), ("B", None), ("C", "2027-01-02")]
    ]
    response = tasks_client.get("/tasks")
    assert response.status_code == 200
    assert response.json() == created
    assert [t["title"] for t in response.json()] == ["A", "B", "C"]


def test_list_tasks_empty(tasks_client: TestClient) -> None:  # AC-001.3
    response = tasks_client.get("/tasks")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "payload",
    [{}, {"title": None}, {"title": ""}, {"title": "   "}, {"title": 5}],
    ids=["missing", "null", "empty", "whitespace", "not-a-string"],
)
def test_invalid_title_is_422_and_creates_nothing(  # AC-001.4
    tasks_client: TestClient, payload: dict[str, Any]
) -> None:
    response = tasks_client.post("/tasks", json=payload)
    assert response.status_code == 422
    assert ["body", "title"] in _locs(response)
    assert tasks_client.get("/tasks").json() == []


def test_title_of_201_characters_is_rejected(tasks_client: TestClient) -> None:  # AC-001.5
    response = tasks_client.post("/tasks", json={"title": "x" * 201})
    assert response.status_code == 422
    assert ["body", "title"] in _locs(response)
    # 201 characters only after trimming: padding must not rescue it
    padded = tasks_client.post("/tasks", json={"title": "  " + "x" * 201 + "  "})
    assert padded.status_code == 422
    assert tasks_client.get("/tasks").json() == []


def test_title_of_200_characters_is_accepted(tasks_client: TestClient) -> None:  # AC-001.5
    response = tasks_client.post("/tasks", json={"title": "x" * 200})
    assert response.status_code == 201
    assert response.json()["title"] == "x" * 200


def test_title_surrounding_whitespace_is_removed(tasks_client: TestClient) -> None:  # AC-001.5
    response = tasks_client.post("/tasks", json={"title": "  Buy milk \n"})
    assert response.status_code == 201
    assert response.json()["title"] == "Buy milk"
    assert tasks_client.get("/tasks").json()[0]["title"] == "Buy milk"


@pytest.mark.parametrize("due", ["2026-02-30", "01.12.2026", "tomorrow", 20261201])
def test_invalid_due_date_is_422_and_creates_nothing(  # AC-001.6
    tasks_client: TestClient, due: Any
) -> None:
    response = tasks_client.post("/tasks", json={"title": "Buy milk", "due_date": due})
    assert response.status_code == 422
    assert ["body", "due_date"] in _locs(response)
    assert tasks_client.get("/tasks").json() == []
