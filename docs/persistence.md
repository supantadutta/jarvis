# Persistence & Migrations

JARVIS uses a **DB-as-source-of-truth, in-memory-as-hydrated-cache** model.

## How it works

- The live app builds the Brain with `persist=True`. The full SQLModel schema is
  migration-managed by **Alembic** (`backend/alembic/`).
- **Write-through:** as they happen, audit entries, approvals, tasks (+ steps),
  chat messages, and **memory chunks** are written to the database via listener
  hooks — the DB is the durable record.
- **Hydration:** on startup the app calls `Brain.hydrate()`, which loads tasks
  and memory back from the DB into the fast in-memory runtime. So state
  **survives restarts**: the in-memory stores are a cache hydrated from the
  durable DB, not the source of truth.

```
write  ──►  in-memory runtime  ──(write-through)──►  SQLModel DB  (source of truth)
read   ◄──  in-memory runtime  ◄──(hydrate on boot)──┘
```

## Migrations (Alembic)

```bash
make migrate                      # alembic upgrade head
make migration m="add x table"    # autogenerate a new revision
# or directly:
cd backend && python -m alembic upgrade head
```

- The DB URL comes from `DATABASE_URL` (SQLite by default; Postgres for scale-up).
- `alembic/versions/0001_initial_schema.py` creates the full baseline schema from
  the SQLModel metadata; later revisions should use autogenerate/`op.*`.
- CI and tests verify `alembic upgrade head` creates all tables, and that tasks +
  memory survive a simulated restart (`test_persistence_hydration.py`).

## Scale-up to Postgres

```env
DATABASE_URL=postgresql+psycopg://jarvis:jarvis@localhost:5432/jarvis
```
Then `make migrate`. No code changes — SQLModel + Alembic handle the dialect.
For background jobs/queues at scale, point the queue at Redis/Arq (the `Job`
API is unchanged).
