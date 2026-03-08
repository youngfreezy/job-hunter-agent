# Railway Deployment — Findings & Learnings

## Live URLs

- **Frontend**: https://frontend-production-96d4b.up.railway.app/
- **Backend**: https://backend-production-1ea9.up.railway.app/

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
Railway uses `.gitignore` to filter which files get uploaded via `railway up`. If `package-lock.json` is gitignored, it won't be available during Docker build. Fix: use `npm install` instead of `npm ci` in the Dockerfile, or add a `.railwayignore` that doesn't exclude the lock file.

### 3. `NEXT_PUBLIC_*` vars are build-time only
Next.js inlines `NEXT_PUBLIC_*` env vars into the JS bundle at build time. Railway injects env vars during Docker build only if they're declared as `ARG` in the Dockerfile. All build-time env vars (including `GOOGLE_CLIENT_ID`, `NEXTAUTH_SECRET`, etc. for NextAuth route compilation) must be declared as `ARG` + `ENV` in the builder stage.

### 4. Railway PORT binding
Railway assigns a dynamic `PORT` env var. The Docker CMD must use `${PORT:-default}` via shell form (`sh -c "..."`) not exec form (`["python", "-m", ...]`). Without this, the service gets a 502 because Railway's proxy can't reach the app.

### 5. No `public/` directory = Docker COPY fails
If the Next.js project has no `public/` directory, `COPY --from=builder /app/public ./public` fails. Fix: `RUN mkdir -p public` before `npm run build`.

### 6. `browser-use` pins strict dependency versions
`browser-use==0.12.1` pins exact versions of `Pillow`, `google-api-python-client`, `pydantic`, `pypdf`, `python-docx`, etc. If `requirements.txt` pins older versions, pip resolution fails. Fix: use `>=` instead of `==` for all packages that browser-use also depends on, and let browser-use drive the versions.

### 7. `playwright` vs `patchright` — both needed
The codebase imports from both `playwright.async_api` (for `TimeoutError`, `Page` types) and `patchright` (for actual browser automation). `patchright` doesn't re-export playwright's types. Both packages must be in `requirements.txt`.

### 8. LangGraph `AsyncPostgresSaver.setup()` + `CREATE INDEX CONCURRENTLY`
`AsyncPostgresSaver.setup()` runs `CREATE INDEX CONCURRENTLY` which cannot execute inside a transaction block. Even with `autocommit=True` on the psycopg connection, this can fail on some Postgres configurations. Fix: wrap `setup()` in a try/except, and create the checkpoint tables manually if needed:

```sql
CREATE TABLE IF NOT EXISTS checkpoints (...);
CREATE TABLE IF NOT EXISTS checkpoint_blobs (...);
CREATE TABLE IF NOT EXISTS checkpoint_writes (...);
```

### 9. Railway private DNS resolution timing
`postgres.railway.internal` DNS resolution can fail during early container startup if the database service isn't fully ready. Using the public proxy URL (`switchback.proxy.rlwy.net:PORT`) is more reliable but adds latency. For production, retry logic on the pool opener or using the public URL is recommended.

### 10. Railway Hobby plan: 3 volume limit
The Hobby plan only allows 3 persistent volumes across all services. Each database addon uses one volume. This means you can have at most 3 database services. Redis was deployed as a volumeless Docker service (`redis:7-alpine`) which is fine for caching/pub-sub but means data is lost on restart.

### 11. pgvector not available on Railway Postgres
Railway's default Postgres image doesn't include pgvector. If vector search is needed, you'd need a custom Postgres Docker image or use a different provider (Supabase, Neon).

## Remaining Manual Steps

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
