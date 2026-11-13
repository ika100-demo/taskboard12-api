# Architecture decision records

| ADR | Decision |
|---|---|
| [001](001-postgres-task-storage.md) | Tasks are stored in Postgres via psycopg 3 async, one connection per call, schema self-created by the service |
