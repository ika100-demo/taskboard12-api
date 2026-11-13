---
spec_id: 001-create-and-list-tasks-in-memory
title: Create and list tasks in memory
status: draft
priority: P1
shape: service-python
---

# 001 — Create and list tasks in memory

## Problem

The taskboard12 Task API so far answers only `/health` and `/ready`; a client (the taskboard12 frontend or a script) has no way to record a task or see the tasks it has. This first feature gives the API its core: create a task with a title and an optional due date, and list all tasks. Tasks are kept in the service's memory only, so the API shape can be used and tested now, before any storage is chosen.

## Stories

As a taskboard12 user (through a client of the API), I want to create a task with a title and, if I like, a due date, so that I can write down what I have to do.

As a taskboard12 user, I want to list all my tasks, so that I can see what is open and when it is due.

## Acceptance criteria

- **AC-001.1** Given the service is running, when a client sends `POST /tasks` with JSON `{"title": "Buy milk", "due_date": "2026-12-01"}`, then the response is `201` with a JSON object containing a server-generated non-empty string `id`, `title` `"Buy milk"`, `due_date` `"2026-12-01"` and `created_at` as an ISO 8601 UTC timestamp. (smoke)
- **AC-001.2** Given the service is running, when a client sends `POST /tasks` with only `{"title": "Call Anna"}`, then the response is `201` with the task object whose `due_date` is `null`.
- **AC-001.3** Given tasks A, B and C were created in that order, when a client sends `GET /tasks`, then the response is `200` with a JSON array containing A, B and C in creation order (oldest first), each with the same `id`, `title`, `due_date` and `created_at` as returned on creation; with no tasks created the array is `[]`. (smoke)
- **AC-001.4** Given the service is running, when a client sends `POST /tasks` with `title` missing, `null`, empty or whitespace only, then the response is `422` with an error whose location names the field `title`, and `GET /tasks` does not contain a new task.
- **AC-001.5** Given the service is running, when a client sends `POST /tasks` with a `title` of 201 characters (after trimming surrounding whitespace), then the response is `422` naming the field `title`; a title of exactly 200 characters is accepted with `201`, and surrounding whitespace is removed from the stored `title`.
- **AC-001.6** Given the service is running, when a client sends `POST /tasks` with a `due_date` that is not a valid calendar date in `YYYY-MM-DD` form (for example `"2026-02-30"`, `"01.12.2026"` or `"tomorrow"`), then the response is `422` with an error whose location names the field `due_date`, and no task is created.
- **AC-001.7** Given tasks were created, when the service is restarted, then `GET /tasks` returns `200` with `[]`.

## Non-goals

- Persistent storage, or sharing tasks between several running instances of the service.
- Reading, updating, completing or deleting a single task.
- Filtering, sorting options, search and pagination of the list.
- Users, accounts and per-user task lists.
- Authentication and access control: anyone who can reach the service may create and list tasks (decided 2026-11-13).
- Due times and time zones (a due date is a calendar date only).

## Assumptions

- **A1** The endpoints are `POST /tasks` and `GET /tasks`, without version prefix (other option: `/v1/tasks`; affects AC-001.1 to AC-001.7).
- **A2** The task fields are `id`, `title`, `due_date`, `created_at`; `id` is an opaque server-generated string (other option: sequential integer ids; affects AC-001.1, AC-001.3).
- **A3** `due_date` is a calendar date `YYYY-MM-DD`; dates in the past are accepted (other option: reject past dates; affects AC-001.6).
- **A4** Title is required, trimmed of surrounding whitespace, 1 to 200 characters (other option: 500 characters, or keep whitespace as sent; affects AC-001.4, AC-001.5).
- **A5** Invalid input answers `422` in the framework's standard validation error format, whose entries name the offending field (other option: `400` with a custom error body; affects AC-001.4 to AC-001.6).
- **A6** The list returns all tasks in creation order, oldest first, with no limit (other option: newest first, or a page size; affects AC-001.3).
- **A7** Unknown fields in the create request are ignored (other option: reject them with `422`; affects AC-001.1).

## Open questions

- ~~May anyone who can reach the service create and list tasks without authentication for now? (suggested: yes, no authentication in this spec, since tasks are in memory and not per user; alternatives: a shared API key from an environment variable, or wait for a users spec; affects AC-001.1 to AC-001.3 or a new criterion)~~ Answered 2026-11-13: yes, no authentication; folded into Non-goals.

## Changelog

- 2026-11-13 created
- 2026-11-13 amended: open question on authentication answered (no authentication); added as a non-goal, criteria unchanged
