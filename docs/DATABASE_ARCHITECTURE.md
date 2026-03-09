# Database Architecture

## Plain English Summary

JobHunter uses two databases: **PostgreSQL** for permanent data and **Redis** for temporary, fast-access data.

**PostgreSQL** is where everything important lives — user accounts, job search sessions, application results, billing/wallet info, autopilot schedules, and the AI pipeline's internal checkpoints. If the server restarts, all of this survives. It's hosted on Railway alongside the rest of the app.

**Redis** handles short-lived stuff that doesn't need to survive a restart: rate limiting (so users can't spam the API), task queues, and coordination between autopilot runs.

### What is connection pooling and why does it matter?

Every time the app talks to Postgres, it needs a "connection" — think of it like a phone call. Without pooling, the app was dialing a brand new call for every single database query, then hanging up immediately after. With autopilot checking every 60 seconds and each job search making 50+ queries, this meant hundreds of rapid-fire dial-and-hangup cycles. That caused three problems:

1. **Slowness** — each new connection takes 50-200ms just to set up (handshake, security, authentication) before any actual work happens.
2. **Connection limits** — Postgres only allows ~100 simultaneous connections. Rapid-fire new connections can hit that ceiling and start failing.
3. **Socket exhaustion** — closed connections linger in the OS for ~60 seconds before fully cleaning up, clogging the network layer.

**The fix: a connection pool.** Instead of dialing a new call every time, the app keeps a small set of open connections ready to go. When code needs the database, it borrows a connection from the pool, does its work, and returns it — no setup cost, no teardown waste. The app maintains two pools: one for regular operations (max 20 connections) and one for the AI pipeline's checkpoint system (max 10 connections). That's 30 total out of Postgres's 100 limit, leaving plenty of room.

---

## Technical Implementation

### Connection Pool Architecture

Two separate pools serve different access patterns:

| Pool | Location | Type | Max Size | Used By |
|------|----------|------|----------|---------|
| Sync pool | `backend/shared/db.py` | `psycopg_pool.ConnectionPool` | 20 | All store modules, route handlers |
| Async pool | `gateway/main.py` | `psycopg_pool.AsyncConnectionPool` | 10 | LangGraph `AsyncPostgresSaver` checkpointer |

**Sync pool config:** `min_size=2` (2 warm connections always ready), `max_size=20`.

```
backend/shared/db.py
├── get_pool()        → returns the shared ConnectionPool (lazy-initialized)
├── get_connection()  → context manager: checks out a connection, returns it on exit
└── close_pool()      → called during FastAPI shutdown
```

### Connection Pattern

Every file that needs Postgres uses the pool through a local `_connect()` wrapper:

```python
from backend.shared.db import get_connection

def _connect():
    return get_connection()

# Usage in any store function:
with _connect() as conn:
    conn.execute("SELECT ...")
    conn.commit()
```

When the `with` block exits, the connection returns to the pool — not destroyed, just available for reuse.

### Pool Lifecycle

- **Startup**: Sync pool is lazy-initialized on first use (typically during `ensure_*_tables()` calls in the FastAPI lifespan). Async pool is explicitly opened in the lifespan.
- **Shutdown**: Both pools are closed in the FastAPI shutdown handler (`close_pool()` for sync, `pool.close()` for async).

### Store Modules

Each store module owns one domain's tables and provides CRUD helpers (sync psycopg calls wrapped with `asyncio.to_thread` where needed):

| Module | Tables | Purpose |
|--------|--------|---------|
| `billing_store.py` | `users`, `wallet_transactions` | User accounts, wallet balance, Stripe |
| `session_store.py` | `sessions` | Job search session state |
| `application_store.py` | `applications` | Individual job application results |
| `autopilot_store.py` | `autopilot_schedules` | Scheduled recurring job searches |
| `selector_memory.py` | `discovery_selectors` | CSS selector learning for job boards |
| `apply_selectors.py` | `apply_selectors` | CSS selector learning for ATS forms |
| `dead_letter_queue.py` | `dead_letter_queue` | Failed operations for retry |

### Rules for New Database Code

1. Import `get_connection` from `backend.shared.db`
2. Always use the `with` context manager pattern
3. Never call `psycopg.connect()` directly — that bypasses the pool
4. Keep transactions short — don't hold a connection while doing network I/O or LLM calls
