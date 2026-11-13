"""In-memory task store."""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime
from uuid import uuid4

from .models import Task


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._lock = threading.Lock()

    def add(self, title: str, due_date: date | None) -> Task:
        task = Task(
            id=str(uuid4()),
            title=title,
            due_date=due_date,
            created_at=datetime.now(UTC),
        )
        with self._lock:
            self._tasks.append(task)
        return task

    def list(self) -> list[Task]:
        with self._lock:
            return self._tasks.copy()
