"""Task endpoints."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request

from .models import Task, TaskCreate
from .store import InMemoryTaskStore

router = APIRouter(tags=["tasks"])
logger = structlog.get_logger(__name__)


def get_task_store(request: Request) -> InMemoryTaskStore:
    store: InMemoryTaskStore = request.app.state.task_store
    return store


StoreDep = Annotated[InMemoryTaskStore, Depends(get_task_store)]


@router.post("/tasks", status_code=201, response_model=Task)
def create_task(payload: TaskCreate, store: StoreDep) -> Task:
    task = store.add(payload.title, payload.due_date)
    logger.info("task_created", task_id=task.id)
    return task


@router.get("/tasks", response_model=list[Task])
def list_tasks(store: StoreDep) -> list[Task]:
    return store.list()
