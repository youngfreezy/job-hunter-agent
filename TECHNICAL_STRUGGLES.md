# Technical Struggles & Help Wanted

## Context

JobHunter Agent is an AI-powered job application automation platform. It discovers jobs via ATS APIs and web search (Bright Data MCP), scores/filters them with LLMs, tailors resumes, and submits applications via Skyvern (visual AI form filler). Built with FastAPI + LangGraph (Python) backend, Next.js frontend, deployed on Railway.

We're looking for help from the open source community on the issues below.

---

## 1. Zero Successful Applications in Production

**The core problem.** Sessions discover jobs and create Skyvern tasks, but end-to-end success rate is near zero.

### Root Causes

- **Auth-walled URLs**: LinkedIn, Indeed, Glassdoor require login to apply. Our discovery pipeline finds these URLs but Skyvern can't get past the login gates.
- **Bot detection**: Even on open ATS platforms (Greenhouse, Lever), Cloudflare/DataDome block headless browsers on Railway's IP ranges.
- **Resume download 404s**: Skyvern couldn't fetch resume files because Railway's `/tmp` is ephemeral (wiped on every deploy). We've since migrated to Postgres BYTEA storage, but this cost us weeks of debugging.
- **CSRF blocking service-to-service calls**: Our CSRF middleware was blocking Skyvern's POST to `/totp-code` and `/resume-file` endpoints (no browser cookies on server-to-server requests).

### What We Need

- Strategies for reliable form filling on ATS platforms without getting blocked
- Alternative to Skyvern that's cheaper and more reliable for structured ATS forms
- Experience with Agent-E's DOM Distillation approach vs. Skyvern's vision-based approach

---

## 2. Discovery Pipeline Fragility

**Current state**: Replaced 10+ hardcoded Playwright scrapers (all broken) with Bright Data MCP `search_engine` + `scrape_as_markdown`.

### Issues

- **LLM-generated search queries are inconsistent**: JSON parsing of LLM output is brittle (regex for `[` and `]`). Falls back to generic queries silently.
- **No fallback when all MCP searches fail**: `all_results = []` → user gets "no jobs found" with no retry.
- **Dedup is weak**: Only compares `title + company`, not URLs. Same job appears multiple times across rounds.
- **Company extraction regex breaks**: Greenhouse URL pattern `/greenhouse.io/(\w+)/` fails on hyphens/underscores in company slugs.
- **ATS-only limitation**: We can only target Greenhouse, Lever, Ashby, Workday, SmartRecruiters. LinkedIn/Indeed/Glassdoor are auth-walled.

### What We Need

- Better job discovery strategies that don't require auth
- Robust dedup across discovery rounds
- Experience with MCP-based agentic search patterns

---

## 3. Session State & Railway Deployment

### Issues

- **In-memory session state**: `session_registry`, `event_logs`, `sse_subscribers` are Python dicts — lost on every deploy/restart.
- **Redis is ephemeral**: Railway hobby plan limits persistent volumes. Redis runs without volume — SSE replay, steering commands, and rate limit state vanish on restart.
- **Stale concurrency counters**: Redis `taskq:active:{user_id}` sets persist across deploys but the sessions they reference are dead. New sessions get 429'd until we flush.
- **LangGraph checkpoint table creation**: `AsyncPostgresSaver.setup()` runs `CREATE INDEX CONCURRENTLY` which fails inside transactions.

### What We Need

- Patterns for persistent session state on ephemeral platforms
- LangGraph checkpoint recovery best practices
- Railway-specific deployment patterns for stateful apps

---

## 4. Skyvern Cost & Reliability

**Skyvern accounts for 95%+ of our Anthropic API spend** (~$50/day at peak).

### Issues

- **Vision-based = expensive**: Every form interaction requires screenshots → Claude vision API calls.
- **No failure categorization**: Skyvern returns generic `failure_reason` strings. We keyword-match them into categories (`auth_required`, `form_error`, `timeout`) which is brittle.
- **Poll loop has no backoff**: Polls every 5s with no max retries. If Skyvern is down, loops forever.
- **Task ID field inconsistency**: Skyvern API returns `task_id` or `id` or `run_id` depending on version. We try all three.
- **30-min timeout is non-deterministic**: Poll-based timing drifts based on response latency.

### Mitigations Applied

- Switched Skyvern from Sonnet to Haiku (6x cheaper)
- Reduced max jobs per session from 20 to 5
- Raised pricing ~65% to hit 70% margins

### What We Need

- Cheaper alternatives to vision-based form filling for structured ATS forms
- Agent-E integration experience (DOM-based, no screenshots)
- Skyvern failure mode documentation / better error handling patterns

---

## 5. Circuit Breaker & Error Handling Gaps

### Issues

- **Content errors bypass circuit breaker**: If LLM consistently outputs malformed JSON, circuit breaker never trips — just silently fails until session timeout.
- **No distinction between transient and permanent errors**: LLM retry logic (5 retries, exponential backoff) wastes budget retrying 401/403 errors.
- **Error categorization via keyword matching**: `error_message.lower()` checked against hardcoded strings. Skyvern/Playwright/LLM errors have inconsistent formats.
- **Silent billing failures**: If `debit_wallet()` throws, it's caught and logged as warning — user's application proceeds but credits aren't deducted.
- **Rate limiting disabled when Redis is down**: Fallback is "allow all requests through."

### What We Need

- Structured error types across the pipeline (not string matching)
- Circuit breaker patterns for LLM content errors (not just connection errors)
- Billing transaction safety patterns

---

## 6. Self-Improvement Loop (Planned)

We want the agent to **learn from its own failures** across sessions. Inspired by [EvoAgentX](https://github.com/EvoAgentX/EvoAgentX).

### Desired Behavior

1. **Log every session outcome** — discovery count, application success/failure, Skyvern errors, which ATS platforms worked
2. **Reflection step** — After each session, LLM reviews logs and suggests improvements to search queries, scoring thresholds, board targeting
3. **Prompt evolution** — Store "best performing" discovery prompts and evolve them based on success rates
4. **Board learning** — Automatically deprioritize ATS platforms with high failure rates

### What We Need

- Experience integrating EvoAgentX with existing LangGraph pipelines
- Self-evolving prompt optimization patterns
- Feedback loop architectures that work in production (not just research)

---

## 7. Frontend UX Gaps

### Issues

- **Blank 429 error message**: `res.statusText` is empty for HTTP 429. UI shows "Failed to start session:" with nothing after the colon. (Fixed but indicative of broader error handling gaps.)
- **SSE reconnection**: No automatic reconnection when backend deploys mid-session. User sees frozen UI.
- **No session recovery UI**: If backend restarts, LangGraph can recover from checkpoints but frontend doesn't know to reconnect.

---

## Stack

| Component | Tech |
|-----------|------|
| Backend | FastAPI + LangGraph (Python 3.11) |
| Frontend | Next.js 14 + Tailwind + shadcn/ui |
| Form Filling | Skyvern (self-hosted, Claude API) |
| Discovery | Bright Data MCP + Greenhouse API |
| Database | Postgres (Railway) |
| Cache/Queue | Redis (Railway, ephemeral) |
| Deployment | Railway |
| Auth | NextAuth.js + JWT |
| Encryption | Fernet (AES-128-CBC + HMAC) |

---

## Contributing

If you have experience with any of these problems, we'd love your input:

- Open an issue with your suggested approach
- PRs welcome for any of the above
- Especially interested in: ATS form filling alternatives, self-improvement loops, Railway deployment patterns
