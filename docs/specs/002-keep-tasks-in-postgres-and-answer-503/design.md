# Design — 002 Keep tasks in Postgres and answer 503 while the database is unreachable

## Decisions

- **Postgres through psycopg 3 (`psycopg[binary]`), async, one short-lived connection per store call.** No pool: a pool's background reconnect and back-off make "re-established on the next request after an outage" (AC-002.6) and "never crash when down at startup" harder to guarantee, and this API's load does not need one. Each call opens a connection, runs its statements and closes it, so recovery after an outage is automatic and needs no state. ADR to create: `postgres-task-storage` ("Tasks are stored in Postgres via psycopg 3 async, one connection per call, schema self-created by the service").
- **Async handlers.** The `/ready` check must give up after 800 ms, but libpq's `connect_timeout` has a 2 s floor; only `asyncio.timeout(0.8)` around an async connect meets it. The store and the task handlers become `async` too, so there is one way to talk to the database.
- **Timeouts** (spec `### Timeouts`): every connection gets `connect_timeout=3` and `options="-c statement_timeout=2000 -c TimeZone=UTC"`; each store call is additionally wrapped in `asyncio.timeout(4.5)` so a `GET`/`POST /tasks` always answers inside 5 s (AC-002.4, AC-002.5). `/ready` uses `asyncio.timeout(0.8)` (AC-002.6).
- **Every storage failure becomes `StorageUnavailableError`**, raised by the store for `psycopg.Error`, `OSError` and `TimeoutError` (refused, timeout, lost connection, statement timeout). One app-level exception handler maps it to `503 {"detail": "Task storage is unavailable"}`; nothing storage-related reaches FastAPI's `500` path. Body validation runs before the handler body touches the store, so an invalid body is `422` even while the database is down (AC-002.5).
- **Schema is created by the service, idempotently, under an advisory lock.** `ensure_schema()` runs `SELECT pg_advisory_xact_lock(<const>)` then `CREATE TABLE IF NOT EXISTS ...` in one transaction, so two replicas starting together do not race. It is attempted once in the app lifespan (failure logged, never raised) and lazily before the first successful store call of a store instance (a flag set after success). A database that is down at startup therefore does not crash the process; the table appears on the first call after it comes back (AC-002.2, AC-002.6).
- **Ordering:** `ORDER BY created_at, seq`, with `created_at` set by the database (`clock_timestamp()`) and `seq` an identity column as tie-break (spec notes, AC-002.1).
- **`DATABASE_URL` is read when `create_app()` runs** (`create_app(database_url: str | None = None)`, defaulting to `os.environ.get("DATABASE_URL")`). Unset: the app still starts, logs `database_url_missing` once, task endpoints answer `503` and `/ready` `503`. There is no in-memory fallback, because a silent fallback would lose data in a misconfigured deployment. The URL is never logged (it carries the password).
- **`InMemoryTaskStore` is removed** (AC-002.1 replaces AC-001.7).
- No gitops change: the system's gitops part already injects `DATABASE_URL` and `PG*`, and the probe paths and port are unchanged.

## Modules

| Module | Responsibility | New / changed |
|---|---|---|
| `src/taskboard12_api/tasks/store.py` | `PostgresTaskStore`, `StorageUnavailableError`, the DDL; `InMemoryTaskStore` removed | changed |
| `src/taskboard12_api/tasks/router.py` | async handlers, `StoreDep` typed to `PostgresTaskStore` | changed |
| `src/taskboard12_api/tasks/__init__.py` | exports `router`, `PostgresTaskStore`, `StorageUnavailableError` | changed |
| `src/taskboard12_api/main.py` | `create_app(database_url=None)`, lifespan schema attempt, `StorageUnavailableError` handler, async `/ready` with DB check | changed |
| `pyproject.toml`, `uv.lock` | `psycopg[binary]>=3.2` (runtime), `testcontainers[postgres]>=4.8` (dev) | changed |
| `docs/env-vars.md` | `DATABASE_URL` row | changed |

Signatures:

```python
# store.py
class StorageUnavailableError(Exception): ...

class PostgresTaskStore:
    def __init__(self, database_url: str | None) -> None: ...
    async def ensure_schema(self) -> None: ...            # raises StorageUnavailableError
    async def add(self, title: str, due_date: date | None) -> Task: ...   # raises StorageUnavailableError
    async def list(self) -> list[Task]: ...               # oldest first; raises StorageUnavailableError
    async def ping(self, timeout: float = 0.8) -> bool: ...   # never raises

# main.py
def create_app(database_url: str | None = None) -> FastAPI: ...
app: FastAPI = create_app()       # builds no connection at import time
```

`created_at` read from the database is normalised with `.astimezone(UTC)`, and `id` (a `uuid` column) is returned as `str(...)`, so the `POST` response (built from `INSERT ... RETURNING`) and every later `GET` produce the same strings (AC-002.1, AC-002.3).

## Contract

Unchanged from spec 001 for `200`/`201`/`422` (task object `id`, `title`, `due_date`, `created_at`; see [001 design](../001-create-and-list-tasks-in-memory/design.md#contract)). New and changed responses, binding for the testers and for taskboard12-web:

| Endpoint | Condition | Status | Body |
|---|---|---|---|
| `GET /tasks` | database reachable | `200` | JSON array of task objects, `ORDER BY created_at, seq` (oldest first), `[]` when none, including on a database without the table (AC-002.1, AC-002.2) |
| `GET /tasks` | storage failure, or `DATABASE_URL` unset | `503` | exactly `{"detail": "Task storage is unavailable"}`, within 5 s (AC-002.4) |
| `POST /tasks` | valid body, database reachable | `201` | the stored task object (AC-002.2, AC-002.3) |
| `POST /tasks` | invalid body (any database state) | `422` | FastAPI validation body as in 001 (AC-002.5) |
| `POST /tasks` | valid body, storage failure | `503` | exactly `{"detail": "Task storage is unavailable"}`; no row inserted (AC-002.5) |
| `GET /ready` | `SELECT 1` succeeds within 800 ms | `200` | `{"status": "ready"}` (AC-002.6) |
| `GET /ready` | otherwise | `503` | `{"status": "unavailable"}` (AC-002.6) |
| `GET /health` | always | `200` | `{"status": "ok"}` (AC-002.6) |

`503` responses are `application/json`. `created_at` is an ISO 8601 UTC timestamp (pydantic writes `Z`), microsecond precision as stored by Postgres; it is byte-identical between the `201` response and later `GET /tasks` responses, also after a restart.

Configuration: `DATABASE_URL` (libpq URI, e.g. `postgresql://user:pass@host:5432/db`). `PG*` variables are not read by the code.

## Data

```sql
CREATE TABLE IF NOT EXISTS tasks (
    seq        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id         uuid        NOT NULL UNIQUE,                 -- uuid4 generated by the service
    title      text        NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    due_date   date        NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

Insert: `INSERT INTO tasks (id, title, due_date) VALUES (%s, %s, %s) RETURNING id, title, due_date, created_at`. List: `SELECT id, title, due_date, created_at FROM tasks ORDER BY created_at, seq`. No migration tool: one table, created by the service; a later schema change brings Alembic in with its own ADR.

## Testing notes (for the testers)

- **Postgres for tests:** a session fixture in `tests/conftest.py` yields a URL: `TEST_DATABASE_URL` when set, else a `testcontainers` `PostgresContainer("postgres:16-alpine")` (Docker is present on the CI runners). Import `testcontainers` inside the fixture, so only database tests fail before t1 adds the dependency. A missing Docker without `TEST_DATABASE_URL` must fail, not skip. A function fixture drops the `tasks` table (`DROP TABLE IF EXISTS tasks`) before each test, so each test starts empty and AC-002.2 starts with no tables. Build apps with `TestClient(create_app(database_url=url))`.
- **Existing tests:** the `client` fixture in `conftest.py` must build a database-backed app, or `test_ready_returns_ready` fails. The 001 tests in `test_tasks.py` keep passing when they get the database URL and the empty table per test; `test_restart_starts_with_empty_list` (AC-001.7) is replaced by AC-002.1 and is removed.
- **Restart (AC-002.1, AC-002.3):** a second `create_app(database_url=url)` on the same database is a new process from the store's point of view (no shared state). Compare the full JSON objects of `POST` responses with the later `GET`.
- **Unreachable (AC-002.4, AC-002.5):** `postgresql://u:p@127.0.0.1:<closed port>/db` answers `503` at once. For "once reachable again" (AC-002.5, AC-002.6), point the app at a small toggleable TCP proxy fixture in front of the test database (closed: refuse; open: forward), so one app instance sees the outage and the recovery without a restart. Assert the `503` arrives within 5 s.
- **Smoke:** the existing read-only `GET /tasks` smoke check now also proves the deployed database is reachable; a `writes` smoke check cannot restart the pod, so persistence across restarts stays an in-process test.
