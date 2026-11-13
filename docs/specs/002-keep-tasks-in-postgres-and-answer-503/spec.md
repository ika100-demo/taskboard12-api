---
spec_id: 002-keep-tasks-in-postgres-and-answer-503
title: Keep tasks in Postgres and answer 503 while the database is unreachable
status: done
priority: P1
shape: service-python
parent: ika100-demo/taskboard12-gitops:001-persist-tasks-in-postgres-and-manage
---

# 002 — Keep tasks in Postgres and answer 503 while the database is unreachable

## Problem

The taskboard12 Task API can create and list tasks (`POST /tasks`, `GET /tasks`), but keeps them in its memory only: every restart or new deployment of the API loses every task, so nobody can rely on the board. And the only way to use it is to call the API directly; the taskboard12 web UI shows nothing about tasks yet. This feature keeps tasks in a Postgres database, so that they survive restarts and deployments, and gives people a page in the web UI to see their tasks and create new ones.

## System context

Slice of the system plan `001-persist-tasks-in-postgres-and-manage` in `ika100-demo/taskboard12-gitops` for `taskboard12-api` (service-python). The system criteria and the contract below are binding: every criterion of this spec implements one of them and names it: `(system AC-<NNN>.<n>)`.

### System criteria

- **AC-001.1** Given tasks were created through `POST /tasks`, when the API is restarted or a new version of it is deployed, then `GET /tasks` returns `200` with the same tasks, each with the same `id`, `title`, `due_date` and `created_at` as returned on creation, in creation order (oldest first).
- **AC-001.2** Given the database cannot be reached by the API, when a client sends `GET /tasks` or `POST /tasks`, then the response is `503` with a JSON body `{"detail": "Task storage is unavailable"}`, no task is created, and the API's readiness check `/ready` answers `503` until the database is reachable again.

### Contract

Caller: the taskboard12-web server (never the browser). Base URL: env `TASKBOARD12_API_URL` (dev: `http://taskboard12-api`). JSON, UTF-8, no authentication.

**Task object** (unchanged):

| Field | Type | Notes |
|---|---|---|
| `id` | string | opaque, server-generated, non-empty |
| `title` | string | trimmed, 1 to 200 characters |
| `due_date` | string `YYYY-MM-DD` or `null` | calendar date, past dates allowed |
| `created_at` | string | ISO 8601 UTC timestamp |

**`GET /tasks`**
- `200`: JSON array of all task objects, creation order (oldest first), no limit, no pagination; `[]` when none.
- `503`: `{"detail": "Task storage is unavailable"}` when the database cannot be reached.

**`POST /tasks`**
- Request: `{"title": string, "due_date": "YYYY-MM-DD" | null}`; `due_date` may be omitted; unknown fields are ignored.
- `201`: the created task object.
- `422`: FastAPI validation error (`{"detail": [{"loc": ["body", "title"|"due_date"], "msg": ..., "type": ...}]}`) for a title missing, null, empty or whitespace only, longer than 200 characters after trimming, or an invalid `due_date`. Validation happens before storage: an invalid body answers `422` even while the database is down.
- `503`: `{"detail": "Task storage is unavailable"}`; no task is created.

**`GET /ready`** (Kubernetes readiness probe): `200` `{"status": "ready"}` when the database answers, else `503`. `GET /health` stays `200` regardless of the database.

No events.

### Errors

- Error format: FastAPI's `{"detail": ...}`; `detail` is a string for `503` (exactly `Task storage is unavailable`) and a list of validation entries for `422`.
- The API answers `503` for every storage failure (connection refused, timeout, lost connection) and never `500` for one; an unexpected exception elsewhere is `500` with FastAPI's default body.
- The web treats any response it does not expect as a failure, without parsing the body: on `GET /tasks` anything but `200` with a JSON array (including `422`, `500`, `503`, a non-JSON body, a connection error) shows `Tasks could not be loaded. Please try again later.`; on `POST /tasks` anything but `201` with a task object shows `The task could not be saved. Please try again.` and keeps the input. A `422` should not occur because the web checks the same limits first; if it does, it is the same save failure. The web does not retry.

### Timeouts

- Web to API, each call (`GET /tasks`, `POST /tasks`): 5 seconds total (`AbortSignal.timeout(5000)`); on timeout or unreachable API, the failure behaviour of `### Errors` (page still loads, form keeps input). A `POST` that timed out may still have created the task; it then appears on the next page load (no live updates, per non-goals).
- API to Postgres: connect timeout 3 seconds, statement timeout 2 seconds, so a `GET`/`POST /tasks` with the database down answers `503` within 5 seconds, inside the web's budget. The connection is re-established on the next request after an outage, without a restart.
- `/ready`'s database check: at most 800 ms (the probe's own timeout is Kubernetes' default 1 second); no answer in time counts as unreachable (`503`).

### Provided by the system

The gitops part of this plan wires these for this repo; rely on them, do not ask for them again:

- resource `postgres`: env `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

### Notes for this repo

Connection from DATABASE_URL (injected by the gitops entry with PG*); the service creates its table itself at
startup if missing, and a database that is down at startup must not crash the process (/health stays 200,
/ready 503). Creation order = ORDER BY created_at, then an insertion sequence as tie-break.

## Stories

<!-- As a <persona>, I want <goal>, so that <benefit>. -->

## Acceptance criteria

- **AC-002.1** Given tasks A, B and C were created through `POST /tasks` in that order, when the service is restarted (a new process with the same `DATABASE_URL`), then `GET /tasks` returns `200` with A, B and C in creation order (oldest first), each with the same `id`, `title`, `due_date` and `created_at` as returned on creation (system AC-001.1) (replaces AC-001.7)
- **AC-002.2** Given the service starts against an empty Postgres database (no tables), when a client sends `GET /tasks`, then the response is `200` with `[]`, and a following `POST /tasks` with `{"title": "Buy milk", "due_date": "2026-12-01"}` answers `201` and is listed by `GET /tasks` (system AC-001.1)
- **AC-002.3** Given tasks are kept in Postgres, when a client sends `POST /tasks` with a title of 200 characters surrounded by whitespace, one with a due date and one without, then `GET /tasks` returns them with the trimmed title, `due_date` as `YYYY-MM-DD` or `null`, and `created_at` as an ISO 8601 UTC timestamp, unchanged after a restart (system AC-001.1)
- **AC-002.4** Given the database cannot be reached, when a client sends `GET /tasks`, then the response is `503` with exactly the JSON body `{"detail": "Task storage is unavailable"}` within 5 seconds (system AC-001.2)
- **AC-002.5** Given the database cannot be reached, when a client sends a valid `POST /tasks`, then the response is `503` with `{"detail": "Task storage is unavailable"}`, and once the database is reachable again `GET /tasks` does not contain that task; an invalid body still answers `422` as before (system AC-001.2)
- **AC-002.6** Given the database cannot be reached, when the readiness check `GET /ready` is called, then it answers `503` while `GET /health` keeps answering `200`; once the database is reachable again, `/ready` answers `200` and `GET /tasks` answers `200` without a restart of the service (system AC-001.2)

## Non-goals

## Assumptions

<!-- Spec 149: decisions taken by default, approved with the spec. One bullet each: - **A1** <the decision> (other option: <…>; affects AC-…). A revised one is struck through (~~…~~), never deleted. -->

## Open questions

<!-- Only what may not be decided by default (spec 149): security or access, money, destroying or migrating data, or a request too ambiguous to build. Approval is refused while any is open. Strike answered ones (~~…~~) and fold the answer into the criteria. -->

## Changelog

- 2026-11-13 created from the system plan, with its criteria (spec 147)
- 2026-11-13 approved
- 2026-11-13 building
- 2026-11-13 done
