# Verification — 001 Create and list tasks in memory

**Result:** pass
**Commit:** 18a0dea · **Base:** a8ab22c · **Trace:** 7/7 criteria named by tests (0 missing)

`cplat quiet test-fast` on 18a0dea: all passed, 5 skipped (the smoke tests, no `SMOKE_BASE_URL`; they run against dev after deploy).

| Criterion | Verdict | Tests | Implementation | Notes |
|---|---|---|---|---|
| AC-001.1 | met | `tests/test_tasks.py::test_create_task_returns_201_with_task_object`; smoke `tests/test_smoke_tasks.py::test_smoke_ac_001_1_create_task` | `src/taskboard12_api/tasks/router.py:25`, `src/taskboard12_api/tasks/store.py:17-25` (`uuid4`, `datetime.now(UTC)`), `src/taskboard12_api/main.py:57` | asserts 201, non-empty string `id`, title, `due_date` `"2026-12-01"`, `created_at` parsed with zero UTC offset |
| AC-001.2 | met | `tests/test_tasks.py::test_create_task_without_due_date_gives_null` | `src/taskboard12_api/tasks/models.py:16` (default `None`), `models.py:34` (`Task.due_date` always serialized) | asserts 201, key present and `null` |
| AC-001.3 | met | `tests/test_tasks.py::test_list_tasks_in_creation_order`, `::test_list_tasks_empty`; smoke `tests/test_smoke_tasks.py::test_smoke_ac_001_3_list_tasks_read_only`, `::test_smoke_ac_001_3_created_tasks_are_listed_in_order` | `src/taskboard12_api/tasks/router.py:32-34`, `src/taskboard12_api/tasks/store.py:28-30` (insertion-order copy) | list equals the three creation responses exactly (all four fields) in order; empty store gives `[]` |
| AC-001.4 | met | `tests/test_tasks.py::test_invalid_title_is_422_and_creates_nothing` [missing, null, empty, whitespace, not-a-string] | `src/taskboard12_api/tasks/models.py:15` (`strip_whitespace=True, min_length=1`) | asserts 422, `["body","title"]` in `loc`, `GET /tasks` stays `[]` |
| AC-001.5 | met | `tests/test_tasks.py::test_title_of_201_characters_is_rejected`, `::test_title_of_200_characters_is_accepted`, `::test_title_surrounding_whitespace_is_removed` | `src/taskboard12_api/tasks/models.py:15` (`max_length=200`, trimming before length check) | 201 chars (also padded) gives 422 naming `title`; 200 chars gives 201; stored and listed title trimmed |
| AC-001.6 | met | `tests/test_tasks.py::test_invalid_due_date_is_422_and_creates_nothing` [`2026-02-30`, `01.12.2026`, `tomorrow`, `20261201`] | `src/taskboard12_api/tasks/models.py:18-28` (before-validator: regex `^\d{4}-\d{2}-\d{2}$` + `date.fromisoformat`) | asserts 422, `["body","due_date"]` in `loc`, no task created |
| AC-001.7 | met | `tests/test_tasks.py::test_restart_starts_with_empty_list` | `src/taskboard12_api/main.py:29-35` (`create_app()` builds a fresh `InMemoryTaskStore`), `main.py:61` (`app = create_app()`) | restart modelled as a second `create_app()`, as `design.md` "Lifetime" defines; store is process memory only, so a real restart behaves the same |

## Non-goals

- Persistent storage / sharing between instances: none; the only store is a `list[Task]` on `app.state` (`store.py:14`). ✔
- Single-task read/update/complete/delete: only `POST /tasks` and `GET /tasks` exist (`router.py:25`, `router.py:32`). ✔
- Filtering, sorting options, search, pagination: `list_tasks` takes no query parameters. ✔
- Users, accounts, authentication: no user model, no auth dependency. ✔
- Due times / time zones: `due_date` is a `date`; datetime strings are rejected (`models.py:23`). ✔
- No template-owned layout change: `main.py` refactor keeps `/health`, `/ready`, `/ping`, `/metrics` paths and responses (moved into `create_app()`); existing health/metrics tests pass. ✔

## Deviations from the plan

- `tests/test_tasks.py`, `tests/test_smoke_tasks.py`, `tests/test_tasks_models.py`, `tests/test_tasks_store.py` are in no task's `files`: acceptable, they are the acceptance tests (test-first) and the tester's unit tests.
- `spec.md` (status `building`), `plan.md`, `design.md` changed: acceptable, pipeline documents.
- t1 is `done: true`; no other task.

## Contract

Matches `design.md`: paths without prefix, 201/200/422, `loc` `["body", "<field>"]`, `due_date` always present, unknown fields ignored (pydantic default), insertion order, `create_app()` factory and signatures as specified. ✔

## Mutation check (report only)

15 of 19 mutants of the changed code were caught by the acceptance tests (79 %; spec 152, report only).

Survived (a test that names the criterion would fail if it checked this):
- `src/taskboard12_api/main.py:40 return value → None`
- `src/taskboard12_api/main.py:45 return value → None`
- `src/taskboard12_api/main.py:50 return value → None`
- `src/taskboard12_api/main.py:55 return value → None`
