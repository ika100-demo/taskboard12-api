# ADR-001: Postgres task storage

**Status:** Proposed (2026-11-13)

## Context

Tasks live in process memory and vanish on every restart. Spec 002 requires them to survive restarts and the API to answer `503` (never crash or answer `500`) while the database is unreachable, with `GET /tasks` and `POST /tasks` answering within 5 s and `/ready` within 800 ms. The system's gitops part already injects `DATABASE_URL`.

## Decision

Tasks are stored in Postgres via psycopg 3 async, one connection per call, schema self-created by the service.

- No connection pool: a pool's background reconnect and back-off make recovery after an outage and surviving a database that is down at startup harder to guarantee, and the load does not need one.
- Async, because only `asyncio.timeout` around an async connect meets the 800 ms `/ready` limit (libpq's `connect_timeout` has a 2 s floor).
- Every storage failure (`psycopg.Error`, `OSError`, `TimeoutError`) becomes `StorageUnavailableError`, mapped to `503`.
- The schema is created idempotently (`CREATE TABLE IF NOT EXISTS` under an advisory lock), once in the lifespan (failure logged, not raised) and lazily before the first successful store call.
- No in-memory fallback: a silent fallback would lose data in a misconfigured deployment.

## Consequences

- Recovery after an outage is automatic and needs no state; each call costs a connection setup.
- Handlers and the store are `async`; tests need a real Postgres (`TEST_DATABASE_URL` or testcontainers).
- A later schema change brings a migration tool (Alembic) with its own ADR.
- `InMemoryTaskStore` is removed.
