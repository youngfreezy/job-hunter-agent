# Railway Deployment — Findings & Learnings

## Live URLs

- **Frontend**: https://jobhunteragent.com (Railway: https://frontend-production-96d4b.up.railway.app/)
- **Backend**: https://api.jobhunteragent.com (Railway: https://backend-production-1ea9.up.railway.app/)
- **Domain registrar**: Namecheap (BasicDNS)

## Architecture

| Service | Type | Notes |
|---------|------|-------|
| Backend (FastAPI + Chromium) | Docker service | Always-on, uses `Dockerfile.backend` |
| Frontend (Next.js standalone) | Docker service | Uses `Dockerfile.frontend` |
| PostgreSQL | Railway database addon | Persistent volume |
| Redis | Docker service (`redis:7-alpine`) | No persistent volume (ephemeral) |

## Key Learnings

### 1. Railway CLI is mostly interactive
The `railway add` and `railway service` commands require interactive terminal prompts. They don't work in non-interactive/CI mode for database provisioning. Workaround: use the Railway GraphQL API at `https://backboard.railway.com/graphql/v2` for programmatic service creation (but it's blocked by Cloudflare for CLI session tokens — need a proper API token from the dashboard).

### 2. `.gitignore` affects Railway uploads
Railway uses `.gitignore` to filter files uploaded via `railway up`. Keep the frontend and marketing package lockfiles tracked and included in uploads. Use `npm ci` in builds so dependency versions match the reviewed lockfile; do not replace it with `npm install` to work around a missing lockfile.

### 3. `NEXT_PUBLIC_*` vars are build-time only
Next.js inlines `NEXT_PUBLIC_*` variables into the JS bundle at build time. Declare these public build inputs as `ARG` + `ENV` in the builder stage. Supply Google OAuth credentials, `NEXTAUTH_SECRET`, and `NEXTAUTH_URL` through the service's runtime environment; the build does not need real authentication secrets. Never pass secrets through Docker `ARG` or persistent build `ENV` ([Docker guidance](https://docs.docker.com/build/building/secrets/)).

### 4. Railway PORT binding
Railway assigns a dynamic `PORT` env var. The Docker CMD must use `${PORT:-default}` via shell form (`sh -c "..."`) not exec form (`["python", "-m", ...]`). Without this, the service gets a 502 because Railway's proxy can't reach the app.

### 5. No `public/` directory = Docker COPY fails
If the Next.js project has no `public/` directory, `COPY --from=builder /app/public ./public` fails. Fix: `RUN mkdir -p public` before `npm run build`.

### 6. `browser-use` pins strict dependency versions
The legacy browser-use dependency set pins versions that conflict with patched public upload parsers. Keep it isolated in `backend/requirements-legacy-browser.txt`; do not relax the production parser constraints to satisfy it. The public image uses `backend/requirements.txt` and Browserbase/Stagehand. See the README's production dependency scope.

### 7. `playwright` vs `patchright` — both needed
The codebase imports from both `playwright.async_api` (for `TimeoutError`, `Page` types) and `patchright` (for actual browser automation). `patchright` doesn't re-export playwright's types. Both packages must be in `requirements.txt`.

### 8. LangGraph `AsyncPostgresSaver.setup()` + `CREATE INDEX CONCURRENTLY`
`AsyncPostgresSaver.setup()` can issue `CREATE INDEX CONCURRENTLY`, which cannot run inside a transaction block. Use the checkpointer's supported setup connection and migrations. Diagnose setup failures before accepting traffic; do not create guessed checkpoint tables or swallow schema errors.

### 9. Railway private DNS resolution timing
`postgres.railway.internal` DNS resolution can fail during early container startup if the database service isn't fully ready. Using the public proxy URL (`switchback.proxy.rlwy.net:PORT`) is more reliable but adds latency. For production, retry logic on the pool opener or using the public URL is recommended.

### 10. Railway Hobby plan: 3 volume limit
The Hobby plan only allows 3 persistent volumes across all services. Each database addon uses one volume. This means you can have at most 3 database services. Redis was deployed as a volumeless Docker service (`redis:7-alpine`) which is fine for caching/pub-sub but means data is lost on restart.

### 11. pgvector not available on Railway Postgres
Railway's default Postgres image doesn't include pgvector. If vector search is needed, you'd need a custom Postgres Docker image or use a different provider (Supabase, Neon).

### 12. Deploy-resilient sessions (zero-downtime deploys)

**Problem**: When Railway deployed a new container, the old container was killed immediately — mid-session Skyvern polls died, SSE connections dropped with 403s, and application results were left in a permanent "pending" state with no way to recover.

**Root causes**:
1. No healthcheck configured → Railway did a hard swap instead of a rolling deploy
2. No graceful shutdown → uvicorn was killed without draining active connections
3. Skyvern `task_id` was only stored after polling completed → if the backend died mid-poll, the task was lost forever
4. `verify_session_owner` compared `int` user_id from JWT against `str` user_id in Redis → 403 on SSE reconnect after deploy

**Fix** (commit `3008ccf`):
1. **`backend/railway.toml`** — added healthcheck config (`/api/health`, 300s timeout). Railway now waits for the new container to pass healthcheck before routing traffic, enabling zero-downtime deploys.
2. **Graceful shutdown** — added 30s `--timeout-graceful-shutdown` to uvicorn so in-flight requests finish before the old container exits.
3. **Persist Skyvern task_id immediately** — `skyvern_applier.py` now writes the `task_id` to `skyvern_task_artifacts` right after Skyvern creates the task (before polling starts). This means even if the backend crashes mid-poll, we know which tasks were in flight.
4. **Skyvern recovery on startup** — new module `backend/shared/skyvern_recovery.py` runs on boot, queries all artifacts with `skyvern_status = 'running'`, re-polls Skyvern for their final status, and updates both the artifact and `application_results` rows. Orphaned tasks are recovered within 10 minutes of a restart.
5. **SSE reconnect fix** — normalized `user_id` to `str()` in `verify_session_owner` so JWT int values match Redis string keys.
6. **DB migration** — added unique constraint on `skyvern_task_artifacts.task_id` to support upsert during recovery.

**Result**: Deploys no longer kill active sessions. Skyvern tasks that were mid-poll are automatically recovered on startup, and SSE clients reconnect seamlessly.

## Remaining Manual Steps

### Trusted proxy configuration

The rate limiter uses the authenticated account identity, or Uvicorn's validated
`request.client.host` for unauthenticated requests. Application code does not read
arbitrary `X-Forwarded-For` values. Set `FORWARDED_ALLOW_IPS` to the exact trusted
immediate ingress peers for your deployment; never trust `*` on a publicly
reachable listener. Uvicorn reads this environment variable itself.

For this Railway deployment, the verified immediate peers on 2026-10-05 were
`100.64.0.1` through `100.64.0.6`, each listed explicitly, plus loopback. These are an observed
deployment configuration, not a universal Railway contract. Recheck peer addresses
after networking changes and confirm that Railway replaces client-supplied
forwarding headers. A missing trusted peer conservatively groups visitors under
that proxy's rate bucket; it must not be fixed by trusting arbitrary headers.

Sensitive auth, submission-start, and verification endpoints return 503 with
`Retry-After` when the shared rate-limit store is unavailable. General read routes
retain their existing availability behavior.

Sources: [FastAPI behind a proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/),
[Railway networking limits and headers](https://docs.railway.com/networking/public-networking/specs-and-limits).

### External service setup

1. **Google OAuth**: Add `https://frontend-production-96d4b.up.railway.app/api/auth/callback/google` to authorized redirect URIs in Google Cloud Console
2. **Stripe Webhook**: Update webhook endpoint to `https://backend-production-1ea9.up.railway.app/api/billing/webhook`
3. **Custom Domain**: `railway domain --set yourdomain.com` per service, then add CNAME records

## Cost Estimate

~$55-70/mo on Railway Pro plan (backend always-on + frontend + Postgres + Redis).

## Redeployment

```bash
cd ~/Desktop/job-hunter-agent

# Deploy backend
railway service backend && railway up -d

# Deploy frontend
railway service frontend && railway up -d

# Check logs
railway service backend && railway logs
railway service frontend && railway logs
```
