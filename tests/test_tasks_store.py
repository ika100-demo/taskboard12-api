"""Unit tests for per-app PostgresTaskStore wiring."""

from __future__ import annotations

import pytest

from taskboard12_api.main import create_app
from taskboard12_api.tasks import PostgresTaskStore

URL = "postgresql://u:p@127.0.0.1:1/db"


def test_create_app_gives_each_app_its_own_store() -> None:
    app1, app2 = create_app(database_url=URL), create_app(database_url=URL)
    assert isinstance(app1.state.task_store, PostgresTaskStore)
    assert app1.state.task_store is not app2.state.task_store


def test_create_app_reads_database_url_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    store = create_app().state.task_store
    assert store._database_url == URL
