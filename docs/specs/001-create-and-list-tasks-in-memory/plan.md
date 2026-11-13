---
spec_id: 001-create-and-list-tasks-in-memory
shape: service-python
spec_hash: ffd4717eee18
summary: POST /tasks and GET /tasks backed by a per-process in-memory store
tasks:
  - id: t1
    title: Add tasks package (model, in-memory store, router) and mount it via create_app()
    files: [src/taskboard12_api/tasks/__init__.py, src/taskboard12_api/tasks/models.py, src/taskboard12_api/tasks/store.py, src/taskboard12_api/tasks/router.py, src/taskboard12_api/main.py]
    covers: [AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7]
    parallel_safe: true
    depends_on: []
    done: true
---

# Plan — 001 Create and list tasks in memory

One task: the model, store and router only become observable once `main.py` mounts them, so splitting them would leave a task whose acceptance checks cannot pass alone, and there is no parallelism to gain. Contract and signatures: [design.md](design.md).

## t1 — Add tasks package (model, in-memory store, router) and mount it via create_app()

**Files:** src/taskboard12_api/tasks/__init__.py, src/taskboard12_api/tasks/models.py, src/taskboard12_api/tasks/store.py, src/taskboard12_api/tasks/router.py, src/taskboard12_api/main.py
**Covers:** AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7
**Goal:** a client can create a task with a trimmed 1–200 character title and an optional `YYYY-MM-DD` due date, and list all tasks oldest first; invalid input answers FastAPI's standard `422` naming the field; tasks live only in the process, in a store owned by the app built by `create_app()`.

**Implementation notes:**
- `models.py`: `TaskCreate` with `title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]` and `due_date: date | None = None`; `Task` with `id: str`, `title: str`, `due_date: date | None`, `created_at: datetime` (aware, UTC). Default `extra="ignore"` (A7).
- `due_date` gets a `field_validator(..., mode="before")`: `None` passes; anything else must be a `str` fully matching `^\d{4}-\d{2}-\d{2}$` and parse with `date.fromisoformat`, else `raise ValueError(...)`. Do not rely on pydantic's lax `date` coercion (accepts ints) or `strict=True` (rejects strings in FastAPI's Python-mode validation).
- `store.py`: `InMemoryTaskStore` holding a `list[Task]` behind a `threading.Lock`; `add(title, due_date)` builds `Task(id=str(uuid4()), created_at=datetime.now(UTC), ...)`, appends, returns it; `list()` returns a copy in insertion order (never sort by `created_at`).
- `router.py`: `router = APIRouter(tags=["tasks"])`; `get_task_store(request: Request) -> InMemoryTaskStore` returns `request.app.state.task_store`; `POST /tasks` (`status_code=201`, `response_model=Task`) and `GET /tasks` (`response_model=list[Task]`). Sync `def` handlers. Response keeps `due_date: null` (no `exclude_none`).
- Log `task_created` with the task `id` via structlog (not the title).
- `main.py`: introduce `create_app() -> FastAPI` that builds the app exactly as today (title/version, `MetricsMiddleware`, FastAPI instrumentation when tracing is enabled, `/health`, `/ready`, `/ping`, `/metrics` registered inside the factory), sets `app.state.task_store = InMemoryTaskStore()` and includes the tasks router. Keep `configure_logging`/`configure_tracing` at module level (once per process) and `app = create_app()`, so uvicorn's `taskboard12_api.main:app` and the existing tests keep working; paths and responses of the existing endpoints do not change.
- `tasks/__init__.py` exports `router` and `InMemoryTaskStore`.
- mypy strict and ruff must pass (`devbox run quality`).

**Done when:** the acceptance tests for AC-001.1 to AC-001.7 pass (in-process via `TestClient(create_app())`, plus the smoke tests for AC-001.1 and AC-001.3), the existing tests (`test_health.py`, `test_metrics.py`, `test_tracing.py`, `test_log_trace.py`) still pass, and `devbox run ci` is green including the coverage gate.
