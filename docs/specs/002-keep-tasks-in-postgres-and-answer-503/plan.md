---
spec_id: 002-keep-tasks-in-postgres-and-answer-503
shape: service-python
spec_hash: 5915170be545
summary: Tasks stored in Postgres (psycopg 3 async, self-created table); 503 and /ready 503 while the database is unreachable
tasks:
  - id: t1
    title: Add PostgresTaskStore with schema, timeouts and StorageUnavailableError
    files: [src/taskboard12_api/tasks/store.py, pyproject.toml, uv.lock, tests/test_tasks_store_postgres.py]
    covers: [AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.5, AC-002.6]
    parallel_safe: true
    depends_on: []
    done: true
  - id: t2
    title: Wire PostgresTaskStore into create_app, async routes, 503 handler and /ready check
    files: [src/taskboard12_api/tasks/store.py, src/taskboard12_api/tasks/router.py, src/taskboard12_api/tasks/__init__.py, src/taskboard12_api/main.py, tests/test_tasks_store.py, docs/env-vars.md]
    covers: [AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.5, AC-002.6]
    parallel_safe: true
    depends_on: [t1]
---

# Plan — 002 Keep tasks in Postgres and answer 503 while the database is unreachable

Two sequential tasks: t1 adds the store next to the in-memory one (nothing wired, existing tests stay green), t2 switches the app to it and removes the in-memory store. The acceptance tests for AC-002.x can only pass after t2. Contract, signatures, DDL and test setup: [design.md](design.md). No gitops task: the system's gitops part already injects `DATABASE_URL`, and port and probe paths are unchanged.

## t1 — Add PostgresTaskStore with schema, timeouts and StorageUnavailableError

**Files:** src/taskboard12_api/tasks/store.py, pyproject.toml, uv.lock, tests/test_tasks_store_postgres.py
**Covers:** AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.5, AC-002.6
**Goal:** an async `PostgresTaskStore` that creates its table if missing, adds and lists tasks in creation order, checks reachability within 800 ms, and turns every storage failure into `StorageUnavailableError`; `InMemoryTaskStore` stays untouched for now.

**Implementation notes:**
- Dependencies: `psycopg[binary]>=3.2` in `dependencies`, `testcontainers[postgres]>=4.8` in the `dev` extra; refresh `uv.lock` (through devbox/uv, never bare `pip`).
- `StorageUnavailableError(Exception)` and `PostgresTaskStore(database_url: str | None)` with the signatures in design.md.
- `_connect()`: `await psycopg.AsyncConnection.connect(url, connect_timeout=3, options="-c statement_timeout=2000 -c TimeZone=UTC")`; `database_url is None` raises `StorageUnavailableError` without connecting.
- `ensure_schema()`: in one transaction `SELECT pg_advisory_xact_lock(<module constant>)` then the `CREATE TABLE IF NOT EXISTS tasks` DDL from design.md; sets `self._schema_ready = True` after commit.
- `add()` / `list()`: wrapped in `asyncio.timeout(4.5)`; one connection per call, run `ensure_schema` statements first when `_schema_ready` is false; SQL exactly as in design.md (`ORDER BY created_at, seq`); `id` generated with `uuid4()`; map rows to `Task` with `id=str(...)`, `created_at=...astimezone(UTC)`.
- Catch `psycopg.Error`, `OSError`, `TimeoutError` in each public method, log `task_storage_unavailable` with `error=type(exc).__name__` only (never the URL), and raise `StorageUnavailableError from exc`.
- `ping(timeout=0.8)`: `asyncio.timeout(timeout)` around connect plus `SELECT 1`; return `False` on any of the above errors or a missing URL, never raise.
- Unit tests in `tests/test_tasks_store_postgres.py` use the testers' Postgres fixture from `conftest.py` (do not edit `conftest.py`): ordering tie-break, idempotent `ensure_schema`, closed-port URL gives `StorageUnavailableError` and `ping() is False`, `None` URL behaviour.
- mypy strict and ruff pass.

**Done when:** `tests/test_tasks_store_postgres.py` passes, all previously passing tests still pass, and `devbox run quality` is green.

## t2 — Wire PostgresTaskStore into create_app, async routes, 503 handler and /ready check

**Files:** src/taskboard12_api/tasks/store.py, src/taskboard12_api/tasks/router.py, src/taskboard12_api/tasks/__init__.py, src/taskboard12_api/main.py, tests/test_tasks_store.py, docs/env-vars.md
**Covers:** AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.5, AC-002.6
**Goal:** the running service keeps tasks in Postgres, answers `503 {"detail": "Task storage is unavailable"}` for storage failures, `/ready` reflects database reachability, `/health` stays `200`, and recovery needs no restart.

**Implementation notes:**
- `main.py`: `create_app(database_url: str | None = None)`; `None` falls back to `os.environ.get("DATABASE_URL")` read at call time; unset logs `database_url_missing` once. `app.state.task_store = PostgresTaskStore(url)`. No connection at construction or import time.
- Lifespan: `await store.ensure_schema()` inside `try/except StorageUnavailableError` (log `task_schema_deferred`, continue).
- `@app.exception_handler(StorageUnavailableError)` returns `JSONResponse(status_code=503, content={"detail": "Task storage is unavailable"})`.
- `/ready` becomes `async`: `200 {"status": "ready"}` when `await store.ping()` is true, else `JSONResponse(503, {"status": "unavailable"})`. `/health`, `/ping`, `/metrics` unchanged.
- `router.py`: `async def` handlers awaiting `store.add` / `store.list`; `get_task_store` and `StoreDep` typed to `PostgresTaskStore`; keep the `task_created` log with the id only.
- Remove `InMemoryTaskStore` from `store.py`; `tasks/__init__.py` exports `router`, `PostgresTaskStore`, `StorageUnavailableError`.
- Rewrite `tests/test_tasks_store.py` (unit tests of the removed in-memory store): drop the in-memory tests, keep one check that each `create_app(database_url=...)` gets its own `PostgresTaskStore`, plus `create_app()` reading `DATABASE_URL` from the environment.
- `docs/env-vars.md`: a "Storage" section with `DATABASE_URL` (no default; unset means tasks answer `503` and `/ready` `503`; injected by the gitops `postgres` resource).
- mypy strict and ruff pass.

**Done when:** the acceptance tests for AC-002.1 to AC-002.6 pass, the spec 001 tests still pass (except the removed AC-001.7 test), `test_health.py` passes with the database-backed `client` fixture, and `devbox run ci` is green including coverage.
