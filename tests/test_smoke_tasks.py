"""Smoke tests for spec 001 (AC-001.1, AC-001.3): they reach the service only via its URL."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import httpx
import pytest

FIELDS = {"id", "title", "due_date", "created_at"}


@pytest.mark.smoke
@pytest.mark.writes
def test_smoke_ac_001_1_create_task(smoke_base_url: str) -> None:  # AC-001.1
    title = f"smoke-{uuid.uuid4()}"
    response = httpx.post(
        smoke_base_url + "/tasks", json={"title": title, "due_date": "2026-12-01"}, timeout=10
    )
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], str) and body["id"]
    assert body["title"] == title
    assert body["due_date"] == "2026-12-01"
    assert datetime.fromisoformat(body["created_at"]).utcoffset() == timedelta(0)


@pytest.mark.smoke
def test_smoke_ac_001_3_list_tasks_read_only(smoke_base_url: str) -> None:  # AC-001.3
    response = httpx.get(smoke_base_url + "/tasks", timeout=10)
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    for item in items:
        assert FIELDS <= set(item)


@pytest.mark.smoke
@pytest.mark.writes
def test_smoke_ac_001_3_created_tasks_are_listed_in_order(smoke_base_url: str) -> None:  # AC-001.3
    ids = []
    for _ in range(2):
        created = httpx.post(
            smoke_base_url + "/tasks", json={"title": f"smoke-{uuid.uuid4()}"}, timeout=10
        )
        assert created.status_code == 201
        ids.append(created.json()["id"])
    listed = [t["id"] for t in httpx.get(smoke_base_url + "/tasks", timeout=10).json()]
    assert ids[0] in listed and ids[1] in listed
    assert listed.index(ids[0]) < listed.index(ids[1])
