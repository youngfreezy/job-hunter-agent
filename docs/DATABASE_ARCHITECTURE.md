# Database Architecture

## Overview

The backend uses PostgreSQL (hosted on Railway) for all persistent state: users, sessions, applications, autopilot schedules, billing/wallets, selector memory, and LangGraph checkpoints.

Redis (also Railway) handles ephemeral state: rate limiting, task queues, and autopilot run coordination.

## Connection Pooling

All synchronous database access goes through a **shared connection pool** defined in `backend/shared/db.py`. This pool is powered by `psycopg_pool.ConnectionPool` (part of the psycopg3 ecosystem).

### Why pooling matters

Before this pool existed, every database call created a brand new TCP connection to Postgres — full TCP handshake, TLS negotiation, and Postgres authentication on every single query. With the autopilot scheduler running every 60 seconds and each job search session making 50+ DB calls, this caused:

- **Connection storms** during pipeline execution (multiple concurrent queries all opening fresh connections)
- **Intermittent failures** when Postgres hit `max_connections` (default 100 on Railway)
- **TIME_WAIT socket exhaustion** from rapid open/close cycles (each closed socket lingers for ~60s)
- **Latency overhead** of 50-200ms per query just for connection setup

### How it works now

```
backend/shared/db.py
├── get_pool()        → returns the shared ConnectionPool (lazy-initialized)
├── get_connection()  → context manager that checks out a connection, returns it on exit
└── close_pool()      → called during FastAPI shutdown
```

Configuration:
- `min_size=2` — always keep 2 warm connections ready
- `max_size=20` — never exceed 20 simultaneous connections from the sync pool

Every store file (`billing_store.py`, `session_store.py`, `application_store.py`, `autopilot_store.py`, `selector_memory.py`, `dead_letter_queue.py`) and route file (`stats.py`, `health.py`, `sms.py`) uses this pool through a local `_connect()` wrapper:

```python
from backend.shared.db import get_connection

def _connect():
    return get_connection()

# Usage in any store function:
with _connect() as conn:
    conn.execute("SELECT ...")
    conn.commit()
```

When the `with` block exits, the connection goes back to the pool — not destroyed, just returned for reuse.

### Two separate pools

There are actually two connection pools:

1. **Sync pool** (`backend/shared/db.py`) — `ConnectionPool`, max 20 connections. Used by all store modules and route handlers for regular CRUD.
2. **Async pool** (`gateway/main.py`) — `AsyncConnectionPool`, max 10 connections. Used exclusively by the LangGraph `AsyncPostgresSaver` checkpointer for checkpoint reads/writes during pipeline execution.

Total max connections: 30 out of Railway's default 100 limit, leaving plenty of headroom.

### Lifecycle

- **Startup**: The sync pool is lazy-initialized on first use (typically during `ensure_*_tables()` calls in the FastAPI lifespan). The async pool is explicitly opened in the lifespan.
- **Shutdown**: Both pools are closed in the FastAPI shutdown handler (`close_pool()` for sync, `pool.close()` for async).

## Store Modules

Each store module owns one domain's tables and provides async CRUD helpers (via `asyncio.to_thread` wrapping sync psycopg calls):

| Module | Tables | Purpose |
|--------|--------|---------|
| `billing_store.py` | `users`, `wallet_transactions` | User accounts, wallet balance, Stripe |
| `session_store.py` | `sessions` | Job search session state |
| `application_store.py` | `applications` | Individual job application results |
| `autopilot_store.py` | `autopilot_schedules` | Scheduled recurring job searches |
| `selector_memory.py` | `discovery_selectors` | CSS selector learning for job boards |
| `apply_selectors.py` | `apply_selectors` | CSS selector learning for ATS forms |
| `dead_letter_queue.py` | `dead_letter_queue` | Failed operations for retry |

## Adding New Database Code

When writing new code that needs Postgres access:

1. Import `get_connection` from `backend.shared.db`
2. Always use the `with` context manager pattern
3. Never call `psycopg.connect()` directly — that bypasses the pool
4. Keep transactions short — don't hold a connection while doing network I/O or LLM calls
