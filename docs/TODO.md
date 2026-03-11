# Remaining Tasks

## Stripe: Test → Live
- [] Activate Stripe account (complete onboarding — business details, bank account, etc.)
- [ ] Swap keys on Railway backend: `STRIPE_SECRET_KEY` → `sk_live_...`
- [ ] Swap keys on Railway frontend: `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` → `pk_live_...`
- [ ] Create new **live mode** webhook in Stripe Dashboard (same URL: `https://api.jobhunteragent.com/api/billing/webhook`, event: `checkout.session.completed`)
- [ ] Update `STRIPE_WEBHOOK_SECRET` on Railway backend with new live `whsec_...`
- [ ] Redeploy frontend (required — `NEXT_PUBLIC_*` vars are build-time)

## Post-Deploy: Autopilot + SMS
- [ ] Install `croniter` and `twilio` in backend venv (`pip install croniter twilio`)
- [ ] Run Alembic migrations (`alembic upgrade head`) — creates `autopilot_schedules` table + adds phone columns to `users`
- [ ] Set Twilio env vars on Railway: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- [ ] Configure Twilio webhook URL: `https://api.jobhunteragent.com/api/sms/webhook` (POST)
- [ ] Run k6 load tests against Railway to establish baselines
- [ ] E2E test: create autopilot schedule → verify cron fires → session runs → email received
- [ ] E2E test: send SMS command → verify response

## Future Features (after 90%+ application success rate)

### Agent Marketplace
- [ ] Public marketplace where users share and monetize custom agents (resume optimizer, salary negotiator, interview coach)
- [ ] Agent composer — drag-and-drop pipeline builder for chaining agents
- [ ] Revenue share model for agent creators
- [ ] Rating/review system for marketplace agents
- [ ] Agent analytics dashboard (usage, success rates, revenue)

### Agent SDK / Developer Platform
- [ ] Open SDK for building custom agents on top of the JobHunter platform
- [ ] Plugin architecture — hook into any pipeline stage (post-discovery, pre-application, post-verification)
- [ ] Webhook system for agent events (job found, application submitted, etc.)
- [ ] API for programmatic agent creation and management
- [ ] Developer documentation and example agents

### Other
- [ ] Proxy rotation for job board scraping (deferred — add when scraper blocks appear)

---

## Recently Completed
- [x] Stripe customer creation on signup (auto-creates in `get_or_create_user`, stored as `stripe_customer_id`)
- [x] Credit auto-refill V1 (notification-based: threshold + pack selector on billing page, low-balance banner)
- [x] Configurable search radius (10–200 mi dropdown, flows through all 4 scrapers)
- [x] US-only restriction (backend country validator + frontend form messaging)
- [x] Company Brief paywall (mission + culture free, rest gated behind session unlock)
- [x] Remove LinkedIn update button (headless browser can't use user's LinkedIn session on Railway)
- [x] Fix CI build crash (NextAuth env var throw at build time → graceful fallback)
- [x] Railway debugging guide (`docs/RAILWAY-DEBUGGING.md`)

## Completed

<details>
<summary>Auth & User Management</summary>

- [x] Real Google OAuth (NextAuth with Google provider, gmail.readonly scope)
  > Implemented NextAuth with Google OAuth provider, requesting `gmail.readonly` scope for verification code extraction. Users authenticate via Google sign-in button, and the JWT session captures email, access token, and refresh token.
- [x] Resolve placeholder `test-user` in sessions.py, payments.py, auth.py routes
  > Replaced all 6 hardcoded `test-user` references with real user resolution via `get_current_user()` helper that extracts email from `X-User-Email` header and calls `get_or_create_user()` to resolve/create the user in Postgres.
- [x] Create user record in Postgres on signup (via get_or_create_user on first API call)
  > The `get_or_create_user(email)` function in `billing_store.py` creates a new user row with UUID, default wallet balance (0.00), and 3 free applications on first encounter. Called automatically on every authenticated API request.
- [x] Add JWT validation middleware on ALL backend routes
  > Implemented `JWTAuthMiddleware` that decrypts NextAuth v4 JWE tokens on every backend request. NextAuth encrypts session tokens using HKDF(SHA-256) key derivation with `NEXTAUTH_SECRET` and AES-256-GCM encryption. The middleware extracts the `Authorization: Bearer <token>` header, decrypts the JWE using the shared secret (HKDF → AESGCM from Python's `cryptography` library, zero new dependencies), extracts the user email from the payload, and sets `request.state.user_email` for downstream route handlers. A new Next.js API route `/api/auth/token` exposes the HttpOnly session cookie to client-side JS, and `api.ts` caches the JWT with a 5-minute TTL. The `X-User-Email` header is accepted as a deprecated fallback with a warning log. This closes the impersonation attack vector where anyone with curl could spoof any user.
- [x] Validate session ownership before returning data (list_sessions filters by user_id)
  > The `list_sessions` endpoint filters all sessions by the authenticated user's ID, preventing users from seeing other users' sessions. Both in-memory registry and Postgres sessions table are filtered.
- [x] Remove E2E auth bypass cookie from production middleware path
  > Removed the `E2E_AUTH_COOKIE` bypass logic from `frontend/src/middleware.ts`. The middleware now purely delegates to NextAuth's `withAuth()` with no backdoor cookies.
- [x] Implement OAuth token exchange server-side instead of passing Gmail tokens client-side
  > Created a Next.js API route `/api/auth/gmail-token` that acts as a server-side proxy. When the session page needs to send Gmail tokens to the backend, it calls this route with just the `session_id`. The route uses NextAuth's `getToken()` to read `googleAccessToken` and `googleRefreshToken` from the JWT server-side (never exposed to the browser), then forwards them to the backend with the user's session token as Bearer auth. The NextAuth session callback no longer includes Google OAuth tokens in the client-facing session object. The old `sendGmailToken()` client-side function was removed entirely. This eliminates the XSS/extension attack surface where tokens were previously readable from `session.user.googleAccessToken`.
</details>

<details>
<summary>Database & Data</summary>

- [x] Session persistence to Postgres (currently Redis-only)
  > Created `sessions` table in Postgres via Alembic migration. Added `session_store.py` with `upsert_session()`, `update_session_status()`, `update_session_counts()`, and `get_sessions_for_user()`. All session status updates and application counts now persist to both in-memory registry and Postgres via `_set_session_status()` and `_set_session_counts()` helpers in `sessions.py`.
- [x] Alembic migrations
  > Set up Alembic migration framework in `backend/alembic/`. Initial migration (`d9617b97a43d`) captures all 6 existing tables plus 2 new ones (sessions, dead_letter_queue). Uses `postgresql+psycopg` dialect and reads `DATABASE_URL` from the app's settings. Run with `cd backend && alembic upgrade head`.
- [x] DELETE endpoint for user data (GDPR) — DELETE /api/auth/me/data
  > The `DELETE /api/auth/me/data` endpoint collects all session IDs from the in-memory registry, deletes application results, billing data (transactions + user row), Redis keys, and in-memory session/event data. Returns 200 on success.
- [x] Exclude resume text from localStorage persistence (PII protection)
  > The SessionWizard form persists state to localStorage under `jh_` prefix but explicitly excludes the `resume_text` field from serialization, preventing PII from lingering in browser storage.
- [x] Clear persisted form data on logout (sign-out button clears jh_ localStorage + sessionStorage)
  > The sign-out button handler iterates all localStorage keys prefixed with `jh_` and removes them, along with clearing sessionStorage, before calling `signOut()`.
</details>

<details>
<summary>Stripe & Billing</summary>

- [x] Wire per-application charging into the pipeline (tiered: 1 cr submitted, 0.5 cr partial, 0 skipped)
  > Added `_charge_for_application()` in `application.py` with tiered pricing: 1.0 credit for submitted, 0.5 for partial/failed (work was done — resume tailored, cover letter generated), 0 for skipped. Charges happen after each application attempt, with free applications consumed first.
- [x] Fix webhook metadata injection — validate credit_amount server-side against PACKS definition
  > The Stripe webhook handler now validates `credit_amount` from checkout metadata against the server-side `PACKS` dictionary, preventing clients from injecting arbitrary credit amounts.
- [x] Validate Stripe redirect URLs on frontend before `window.location.href` assignment
  > Added URL validation before Stripe redirect to ensure the URL starts with `https://checkout.stripe.com/`, preventing open redirect attacks.
- [x] Credit-based pricing model (1 cr submitted, 0.5 cr partial, 0 skipped)
  > Replaced dollar-based pricing with credit-based: packs of 20 ($29.99), 50 ($64.99), 100 ($119.99) credits. Each successful application costs 1 credit, partial attempts (failed after work done) cost 0.5 credits, skipped jobs cost 0 credits. Every user gets 3 free applications.
- [x] Row-level locking on debit_wallet (SELECT FOR UPDATE, RETURNING)
  > `debit_wallet()` uses `SELECT ... FOR UPDATE` to acquire a row-level lock before checking balance, preventing concurrent double-debit race conditions. The `UPDATE ... RETURNING wallet_balance` clause atomically returns the new balance.
- [x] Pre-flight credit check before each application attempt
  > `check_sufficient_credits()` is called before every application attempt in `_apply_to_job()`. If the user has no free applications remaining and insufficient wallet balance, the job is skipped with an actionable message directing them to the billing page.
- [x] Free application transactions display correctly (blue FREE badge)
  > Free application transactions are recorded with type `free_application` and show a blue "FREE" badge in the billing UI, distinguishing them from paid credit transactions.
- [x] Tiered transaction display (green/amber/red for credit/partial/debit)
  > The billing page uses color-coded badges: green for credit additions, amber with "partial" label for `application_partial` charges (0.5 cr), red for full debits, and blue "FREE" for free applications.
</details>

<details>
<summary>Server Components Refactor</summary>

- [x] Migrate client-side data fetching to server-side where possible
  > Converted dashboard and session layouts to async Server Components. Client interactivity (pathname detection, params) moved to leaf `"use client"` shell components (`DashboardShell`, `SessionShell`). Pages with SSE streaming remain client components since EventSource is browser-only.
- [x] Convert pages/layouts to async Server Components
  > Both `(dashboard)/layout.tsx` and `(session)/session/[id]/layout.tsx` are now Server Components that import and render small `"use client"` shell components, reducing the client-side JavaScript bundle.
- [x] Move client interactivity into smaller `"use client"` leaf components
  > Created `DashboardShell.tsx` (handles `usePathname()` for landing page bypass) and `SessionShell.tsx` (handles `useParams()` for session ID). These are the only client components in the layout tree.
- [x] Verify SSE/streaming still works correctly after refactor
  > SSE streaming pages (session details, career pivot, freelance, interview prep) remain `"use client"` components and are unaffected by the layout refactor. EventSource connections work the same since they're leaf components.
</details>

<details>
<summary>Security — Critical</summary>

- [x] CORS: restrict Vercel regex from `.*\.vercel\.app` to specific app domain
  > Changed the CORS `allow_origin_regex` from `.*\.vercel\.app` (which would match any Vercel app) to `job-hunter-agent(-[a-z0-9]+)?\.vercel\.app`, restricting to only this project's preview and production deployments.
- [x] Redis: enable authentication (requirepass in docker-compose, password in REDIS_URL)
  > Added `--requirepass` to the Redis container command in `docker-compose.yml` and updated `REDIS_URL` default in `config.py` to include the password. Health check also passes the password.
- [x] Postgres: change default credentials (now uses env vars with dev defaults)
  > Docker compose now uses `${POSTGRES_USER:-jobhunter}`, `${POSTGRES_PASSWORD:-jobhunter_dev}` environment variable overrides instead of hardcoded credentials. Production deployments set these via environment.
- [x] Umami: change default `APP_SECRET` (now uses env var)
  > The Umami analytics container now reads `APP_SECRET` from `${UMAMI_APP_SECRET:-umami-dev-secret}` environment variable instead of the default insecure value.
- [x] Add CSRF tokens on all state-changing API calls
  > Implemented double-submit cookie CSRF protection. Backend `CSRFMiddleware` sets a `csrf_token` cookie on every response and validates that POST/PUT/PATCH/DELETE requests include a matching `x-csrf-token` header. Frontend `api.ts` reads the cookie via `getCsrfToken()` and includes the header on all state-changing requests. Health, SSE stream, and Stripe webhook endpoints are exempt.
</details>

<details>
<summary>Security — High</summary>

- [x] Add security headers (HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy)
  > Added comprehensive security headers via Next.js `headers()` config: `Strict-Transport-Security`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy` restricting camera, microphone, and geolocation.
- [x] Add file size limit on resume upload endpoint (10MB)
  > The `/parse-resume` endpoint validates uploaded file size against a 10MB limit before processing, returning a 413 error with a descriptive message if exceeded.
- [x] Fix path traversal in resume file handling — UUID-only filenames
  > Resume files are saved with UUID-generated filenames (e.g., `a1b2c3d4.pdf`) instead of user-provided filenames, eliminating path traversal risks like `../../etc/passwd`.
- [x] Fix screenshot path validation — use `Path.is_relative_to()` instead of string prefix match
  > Screenshot path validation now uses `Path.is_relative_to()` which properly handles `..` segments, instead of the bypassable `str.startswith()` check.
- [x] Validate file content-type with magic bytes, not just extension
  > Resume upload validates file content by reading magic bytes (PDF `%PDF`, DOCX PK zip header) in addition to checking the file extension, preventing malicious file uploads disguised as documents.
- [x] Redact PII/resume text from debug logs (page body snippets, form fields, stack traces)
  > Log output is sanitized to remove resume text, form field values, and page body content. Error messages sent to clients use generic text instead of raw exception details.
- [x] Auth-gate `/test-apply` endpoint (requires authenticated user)
  > The `/test-apply` endpoint now calls `get_current_user(request)` which raises 401 if no valid JWT is present, preventing unauthenticated access to the test application feature.
- [x] Don't store OAuth refresh tokens in JWT session — use server-side token store (Gmail tokens now in Redis)
  > Gmail OAuth tokens (access + refresh) are stored in Redis under `gmail_token:{session_id}` keys with a 2-hour TTL, instead of being embedded in the JWT session cookie.
- [x] Pin dependency versions to exact patch levels in requirements.txt and package.json
  > All Python dependencies in `requirements.txt` use exact `==` version pins (e.g., `fastapi==0.115.6`). Frontend `package.json` uses exact versions without `^` or `~` prefixes.
</details>

<details>
<summary>Security — Medium</summary>

- [x] Add rate limiting to `/test-apply` endpoint (3/60s)
  > The `/test-apply` endpoint is rate-limited to 3 requests per 60 seconds per IP address using the Redis-backed rate limiter middleware.
- [x] Tighten session creation rate limit (5/min → 2/min)
  > Session creation (`POST /api/sessions`) is limited to 2 requests per minute per IP, down from the previous 5/min limit, preventing rapid session creation abuse.
- [x] Don't return raw exception details to clients — use generic error messages
  > All exception handlers now return generic messages like "An internal error occurred" instead of raw stack traces or exception messages. Detailed errors are logged server-side only.
- [x] Handle Redis-down gracefully without disabling rate limiting entirely (allows requests through on Redis failure)
  > When Redis is unavailable, the rate limiter allows requests through with a debug log, instead of either blocking all requests or disabling rate limiting entirely.
- [x] Validate `resume_file_path` parameter in StartSessionRequest (field_validator)
  > The `StartSessionRequest` Pydantic model includes a `field_validator` for `resume_file_path` that rejects paths containing `..` segments or absolute paths, only allowing UUID-based filenames.
- [x] Validate API base URL strictly — fail if NEXT_PUBLIC_API_URL not set in production
  > The `_resolveApiBase()` function in `api.ts` throws an error if `NEXT_PUBLIC_API_URL` is not set when `NODE_ENV === "production"`, preventing the frontend from silently falling back to localhost.
- [x] Don't log DATABASE_URL (even truncated — leaks host/user/port)
  > Removed all logging of `DATABASE_URL` from startup and error paths. Connection details are no longer visible in log output.
</details>

<details>
<summary>Resilience</summary>

- [x] Circuit breaker pattern for external API calls (job boards, LLM)
  > Implemented `CircuitBreaker` class in `circuit_breaker.py` with three states (CLOSED, OPEN, HALF_OPEN). Pre-configured breakers for LLM (5 failures, 60s recovery), job boards (8 failures, 120s recovery), and Bright Data (3 failures, 90s recovery). Integrated into `invoke_with_retry()` in `llm.py` — when the circuit opens, requests are immediately rejected with `CircuitBreakerOpen` instead of waiting for timeouts.
- [x] Retry with exponential backoff on transient failures (LLM: 429/500/502/503/timeout, browser: goto_with_retry)
  > `invoke_with_retry()` uses exponential backoff with jitter: `min(60, 10 * 2^attempt) + random(0,1)` seconds. Retryable errors include status codes 429/500/502/503/529, timeouts, and connection errors. Browser navigation uses `goto_with_retry()` with 2 max retries.
- [x] Dead letter queue for failed applications
  > Created `dead_letter_queue` table in Postgres and `dead_letter_queue.py` store module. Failed applications are automatically enqueued with job details, error message, error type, and a retry-after timestamp. Supports `get_pending_items()`, `mark_resolved()`, `increment_attempt()`, and GDPR `delete_for_sessions()`. Integrated into the application agent's exception handler.
- [x] Health check endpoint that verifies all dependencies (/api/health/ready checks DB + Redis)
  > The `/api/health/ready` endpoint verifies Postgres connectivity (executes `SELECT 1`) and Redis connectivity (executes `PING`), returning 200 only if both are healthy.
</details>

<details>
<summary>DevOps & CI/CD</summary>

- [x] CI/CD pipeline (GitHub Actions — backend tests, frontend build, lint)
  > GitHub Actions workflow in `.github/workflows/ci.yml` runs three parallel jobs: `backend-tests` (Python 3.11 with Postgres and Redis service containers, runs pytest), `frontend-build` (Node 20, runs `npx next build`), and `lint` (runs `npx next lint`). Triggered on push/PR to main.
- [x] Sentry error tracking (init in main.py, env var SENTRY_DSN)
  > Sentry SDK initializes in `main.py` when `SENTRY_DSN` is set, with `FastApiIntegration` (endpoint-style transactions), `LoggingIntegration` (captures WARNING+ as breadcrumbs, ERROR+ as events), 10% trace sampling, and `send_default_pii=False`. Gracefully skips if `sentry-sdk` is not installed.
- [x] Resend transactional email (domain verified, DNS records in Namecheap, API key on Railway)
  > Sends session-complete summary and application-failed notifications via `notifications@jobhunteragent.com`. Domain verified with DKIM, SPF, and DMARC records.
- [x] Railway health checks for blue/green deploys (backend `/api/health/ready` 150s, frontend `/` 60s)
  > Configured in Railway dashboard. New containers must pass health check before traffic switches, enabling zero-downtime deploys.
- [x] Bright Data integration on Railway (CAPTCHA-solving browser for Indeed/Glassdoor)
  > Set `BRIGHT_DATA_BROWSER_ENABLED`, `BRIGHT_DATA_BROWSER_USE_FOR_DISCOVERY`, `BRIGHT_DATA_BROWSER_CDP_URL`, `BRIGHT_DATA_BROWSER_BOARDS`, and `BRIGHT_DATA_API_TOKEN` on Railway backend.
- [x] Stripe webhook configured (live endpoint on Railway, `STRIPE_WEBHOOK_SECRET` set)
  > Webhook at `https://api.jobhunteragent.com/api/billing/webhook` listening for `checkout.*` events.
- [x] LangSmith/LangGraph tracing (env vars LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY)
  > LangChain/LangGraph auto-detects tracing when `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` are set. The `LANGCHAIN_PROJECT` setting defaults to `"job-hunter-agent"`. No code changes needed — the SDK handles trace collection automatically.
</details>

<details>
<summary>Testing</summary>

- [x] Backend security unit tests (upload, error sanitization, rate limiting, CORS)
  > Test suite in `backend/tests/` covers: file upload validation (size limits, magic bytes, path traversal), error message sanitization (no raw exceptions in responses), rate limiting behavior, and CORS header verification.
- [x] Backend input validation tests (verify Pydantic models reject bad data)
  > Tests verify that Pydantic request models (`StartSessionRequest`, etc.) reject invalid inputs: malformed emails, path traversal attempts in `resume_file_path`, oversized strings, and missing required fields.
</details>

<details>
<summary>Application Safeguards</summary>

- [x] Company application rate limit: max 2 applications per company per 2-week window
  > `check_company_rate_limit()` in `application_store.py` queries submitted applications by company name (case-insensitive) within a 14-day window. If 2+ submissions exist, the application is skipped with a descriptive message.
- [x] Validate against application_results table before submitting
  > `check_already_applied()` checks the `application_results` table for any prior submission with the same `job_id` and `status='submitted'`, preventing duplicate applications to the same job listing.
</details>
