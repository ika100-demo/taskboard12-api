# Design — 001 Create and list tasks in memory

## Decisions

- **One `tasks` package with model, store and router**, mounted on the existing FastAPI app. It follows the template's layout (`src/taskboard12_api/`) and adds no new dependency: FastAPI and pydantic v2 already cover validation and the standard `422` format (A5).
- **The store lives on `app.state`, built by an app factory.** `main.py` gets `create_app() -> FastAPI`, which builds a fresh app with a new empty `InMemoryTaskStore` in `app.state.task_store`; the module keeps `app = create_app()` for uvicorn and the existing tests. A new `create_app()` behaves exactly like a restarted process (AC-001.7), and tests get an empty store per test without reaching into module globals (AC-001.3 "no tasks → `[]`").
- **The store is a process-local list behind a `threading.Lock`.** Sync endpoints run in FastAPI's thread pool, so append and snapshot must be atomic. List order is insertion order, never sorted by `created_at`, because two tasks can share a timestamp (AC-001.3, A6).
- **`due_date` is validated by a `mode="before"` validator, not by pydantic's `date` coercion.** Pydantic's lax `date` parsing also accepts unix timestamps (ints) and some datetime strings, which the spec rejects; FastAPI validates in Python mode, so `strict=True` would reject every JSON string. The validator accepts `None` or a string that fully matches `^\d{4}-\d{2}-\d{2}$` and is a real calendar date (`date.fromisoformat`); otherwise it raises `ValueError` (AC-001.6).
- **`title` uses pydantic `StringConstraints(strip_whitespace=True, min_length=1, max_length=200)`**, so trimming happens before the length check (AC-001.4, AC-001.5, A4).
- **Unknown request fields are ignored** (pydantic default `extra="ignore"`, A7).
- No ADR: the in-memory store is deliberately temporary (the spec defers storage), and the factory is local to this service's `main.py`.
- Operational note (no gitops change): each replica holds its own tasks. With more than one replica, `GET /tasks` answers from whichever pod serves it; the spec makes this a non-goal.

## Modules

| Module | Responsibility | New / changed |
|---|---|---|
| `src/taskboard12_api/tasks/__init__.py` | exports `router`, `InMemoryTaskStore` | new |
| `src/taskboard12_api/tasks/models.py` | `TaskCreate` (request), `Task` (stored + response), the `due_date` validator | new |
| `src/taskboard12_api/tasks/store.py` | `InMemoryTaskStore`: `add(title, due_date) -> Task`, `list() -> list[Task]` | new |
| `src/taskboard12_api/tasks/router.py` | `APIRouter` with `POST /tasks`, `GET /tasks`; `get_task_store(request)` dependency reading `request.app.state.task_store` | new |
| `src/taskboard12_api/main.py` | `create_app()` factory, mounts the router, sets `app.state.task_store`; `app = create_app()` | changed |

Signatures:

```python
# models.py
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

class TaskCreate(BaseModel):
    title: Title
    due_date: date | None = None          # before-validator: None | "YYYY-MM-DD" real date

class Task(BaseModel):
    id: str                                # str(uuid4())
    title: str
    due_date: date | None
    created_at: datetime                   # timezone-aware, UTC

# store.py
class InMemoryTaskStore:
    def add(self, title: str, due_date: date | None) -> Task: ...
    def list(self) -> list[Task]: ...      # a copy, oldest first

# main.py
def create_app() -> FastAPI: ...
app: FastAPI = create_app()
```

## Contract

No authentication (spec non-goal). No version prefix (A1). JSON in and out.

### `POST /tasks`

Request body (JSON object):

| Field | Type | Rules |
|---|---|---|
| `title` | string | required; surrounding whitespace removed; then 1–200 characters |
| `due_date` | string `YYYY-MM-DD` or `null` | optional, default `null`; must be a real calendar date; past dates accepted (A3) |
| any other field | — | ignored (A7) |

`201 Created`, body: the task object (AC-001.1, AC-001.2):

```json
{"id": "3b0c6c1e-2f4a-4a51-9d6e-2b1f0f7f3e2a", "title": "Buy milk", "due_date": "2026-12-01", "created_at": "2026-11-13T09:30:00.123456Z"}
```

| Field | Type | Meaning |
|---|---|---|
| `id` | string | server-generated, non-empty, opaque (a UUID4 today; clients must not parse it) |
| `title` | string | the trimmed title |
| `due_date` | string `YYYY-MM-DD` or `null` | always present; `null` when not sent or sent as `null` |
| `created_at` | string | ISO 8601 / RFC 3339 UTC timestamp with `Z` suffix; fractional seconds may be present or absent. Tests should parse it with `datetime.fromisoformat` and assert a zero UTC offset rather than compare the string. |

`422 Unprocessable Entity`: FastAPI's standard validation body (A5); no task is created:

```json
{"detail": [{"type": "string_too_short", "loc": ["body", "title"], "msg": "...", "input": "   ", "ctx": {"min_length": 1}}]}
```

Each entry of `detail` has `type`, `loc`, `msg`, `input` (and sometimes `ctx`). `loc` names the field as `["body", "<field>"]`. Clients and tests must match on `loc`, not on `msg` or `type`, which are pydantic's wording.

| Input | `loc` | Typical `type` | Criterion |
|---|---|---|---|
| `title` missing | `["body","title"]` | `missing` | AC-001.4 |
| `title` `null` or not a string | `["body","title"]` | `string_type` | AC-001.4 |
| `title` `""` or whitespace only | `["body","title"]` | `string_too_short` | AC-001.4 |
| `title` > 200 characters after trimming | `["body","title"]` | `string_too_long` | AC-001.5 |
| `due_date` not a `YYYY-MM-DD` string or not a real date (`"2026-02-30"`, `"01.12.2026"`, `"tomorrow"`, `20261201`) | `["body","due_date"]` | `value_error` | AC-001.6 |
| body not valid JSON / not an object | `["body", ...]` | `json_invalid` / `model_attributes_type` | — |

### `GET /tasks`

`200 OK`, body: a JSON array of task objects (same shape and values as returned by `POST /tasks`), in creation order, oldest first, no limit; `[]` when none exist (AC-001.3, A6).

### Lifetime

Tasks exist only in the memory of the process; a restart (in tests: a new `create_app()`) starts with `[]` (AC-001.7).

## Testing notes (for the testers)

- In-process tests should build a fresh app per test, `TestClient(create_app())` from `taskboard12_api.main`, so the store starts empty; AC-001.7 is shown by creating tasks on one `create_app()` and listing on a second one.
- Smoke (AC-001.1, AC-001.3 are marked smoke): the create check is `@pytest.mark.smoke` + `@pytest.mark.writes` with a title `smoke-<uuid>`; the list check against a shared instance cannot assume `[]` or exact contents, so the read-only smoke check asserts `200` with a JSON array whose items have the four fields, and the writing one asserts the created task appears after earlier ones.

## Data

No persistent data. One `list[Task]` per process in `app.state.task_store`.
