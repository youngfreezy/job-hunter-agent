# Review: Browserbase rebuild, cloud-agent pass (2026-10-03)

Branch: `browserbase-mode`. Seven commits, one per deliverable in `tasks/todo.md`, plus this review.
Nothing was run against a live job site or a live Browserbase account; all external calls are mocked in tests.

## What changed

| # | Commit | Summary |
|---|--------|---------|
| 1 | `Make DB-backed and network-touching tests deterministic` | `asyncio.run()` instead of `get_event_loop()` in the Gmail/double-submit tests; `backend/tests/conftest.py` skips `requires_postgres` tests with the connection error as the reason instead of erroring after a 30 s pool timeout; the Greenhouse/Lever API applier tests stub `aiohttp` instead of calling the live ATS APIs. |
| 2 | `Add per-user application rules to scoring and form filling` | `users.application_rules` (alembic `n1a2b3c4d5e6` + runtime `ALTER` in `billing_store`), `GET/PUT /api/auth/me/application-rules`, Settings textarea. `backend/shared/application_rules.py` formats the delimited "Owner's application rules" block that `scoring.py` and `form_filler.analyse_form` append. `FormAnalysisResult.park_question` → `ApplicationParked` → `BaseApplier.run` returns `SKIPPED` with the exact question in `error_message`. |
| 3 | `Verify shortlist candidates are open via the Browserbase Fetch API` | `backend/browser/fetch_verifier.py`: `POST /v1/fetch` (markdown), closed-copy and Apply-control checks, `JobListing.verified_open` / `verify_note`, "Verified open" badge on job cards. Runs in `scoring.py` on the top `max_jobs + 10` candidates before the cap; drops only listings positively found closed/apply-less. |
| 4 | `Embed the Browserbase Live View in the session page` | `browser_live_view` SSE event → `src/lib/liveView.ts` → `LiveBrowserPanel` iframe above the Live Status feed (provider must be `browserbase`, URL must be https). vitest added as the frontend unit test runner (`npm test`). |
| 5 | `Add per-user Browserbase settings and a sign-in capture flow` | `browserbase_settings` table (alembic `o2b3c4d5e6f7`; API key Fernet-encrypted, never echoed), `BrowserbaseConfig` + `config_for_user()` layered over env settings and used by `BrowserManager`, the application node and the verifier. `POST /api/browserbase/login-sessions` creates a Context, starts a `persist: true` session, returns the Live View URL; `login_capture.py` polls cookies for the board's login cookie (Indeed: `PPID`), waits 4 s, closes the browser, stores the Context id. Settings UI section with the embedded Live View. |
| 6 | `Add an Indeed Apply applier for logged-in Browserbase contexts` | `ATSType.INDEED`, URL detection, `appliers/indeed.py` registered in `dispatcher.py`. Application-node pre-flights let Indeed/Easy-Apply jobs through only when the user has an Indeed Context. |
| 7 | `Refresh dependency floors and run CI on the branch` | `backend/requirements.txt` floors raised to the versions resolved and tested today, caps on majors not exercised; in-range `npm update` of three packages; `ci.yml` now triggers on `browserbase-mode`/`staging`, runs backend tests on Python 3.11 and 3.12, adds `npm test` and `tsc --noEmit`. |

Not done: the todo's Skyvern item (remove the Skyvern-credits abort path from the Browserbase branch) was not in the
enumerated deliverables and was left untouched.

## Verified

- Backend: `python -m pytest backend/tests -q` → **237 passed** on Python 3.12 against a local Postgres 16 + Redis 7
  (and with Postgres down: the 14 `requires_postgres` tests skip with the connection error as the reason, nothing errors).
- Frontend: `npm test` (7 vitest tests), `npx tsc --noEmit`, `npx next lint` (only the pre-existing `ConfigStep.tsx`
  warning), `npx next build` — all green after every frontend change.
- Existing Browserbase tests (`test_browserbase_mode.py`) still pass with the optional `config` argument; the
  two assertions on `release_session` were loosened to check the positional session id.
- Owner rules honoured: no AI attribution in commits; no silent mock fallback in production paths (the verifier
  and rules loader log/propagate instead of pretending); every feature has tests.

## Unverified (needs a live run)

- **Browserbase Fetch API field names.** `fetch_verifier.py` sends `{"url", "format": "markdown", "projectId"}`
  and reads `markdown` / `content` / `text` (also nested under `data` / `result`) plus `statusCode` / `finalUrl`.
  The reference docs were unreachable from the sandbox. Marked `TODO(unverified)`; a response without a markdown
  body raises `BrowserbaseError`, so a schema mismatch shows up as `verifier error:` on every listing (listings
  are kept, not dropped) rather than as "verified".
- **Indeed Apply selectors** in `backend/browser/tools/appliers/indeed.py` (`_APPLY_BUTTON`, `_CONTINUE_BUTTON`,
  `_SUBMIT_BUTTON`, `_SIGNED_OUT`) — the repo's seed selectors, never checked against the live DOM from this
  code base. `SELECTORS_VERIFIED = False`; a miss returns `FAILED` naming the group and selectors. Flip the flag
  and drop the TODO once they are confirmed with a logged-in context.
- **Login capture end-to-end** (`login_capture.py`): the CDP cookie poll, 4 s settle and close-to-persist sequence
  mirrors the owner's script and is unit-tested with a fake Playwright, but has not been run against Browserbase.
  Only Indeed is enabled; other boards need their login cookie confirmed first.
- **Live View iframe embedding**: the Live View URL is said to be embeddable; the iframe has no sandbox attribute
  so takeover input works, but this was not exercised in a browser.
- **Alembic migrations** `n1a2b3c4d5e6` and `o2b3c4d5e6f7` were not applied with `alembic upgrade` here (the
  stores also create/alter on first use, which is what the tests exercise). Run them on the deployment DB.
- **CI on GitHub Actions**: the workflow now triggers on this branch; the first run is the push of commit 7.
  The Python 3.11 leg was additionally checked locally (see the final message / `pytest` on a 3.11 venv).

## Commands to run locally

```bash
git fetch origin && git checkout browserbase-mode

# Backend
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r backend/requirements.txt
docker compose up -d postgres redis            # or any Postgres on :5433 / Redis on :6379
python -m pytest backend/tests -q              # expect 237 passed (14 skip with a reason if Postgres is down)
cd backend && alembic upgrade head && cd ..    # applies n1a2b3c4d5e6 + o2b3c4d5e6f7

# Frontend
cd frontend && npm ci
npm test                                       # vitest, 7 tests
npx next lint && npx tsc --noEmit
NEXT_PUBLIC_API_URL=http://localhost:8000 NEXTAUTH_SECRET=dev npm run build

# Try it
npm start                                      # from the repo root (Docker + backend + frontend)
# Settings → Application Rules: paste rules, Save.
# Settings → Browserbase: API key + project id, Save, then "Sign in to Indeed" and log in inside the panel;
#   the Indeed Context id fills in when the PPID cookie appears. Save again.
# Start a session with BROWSER_MODE=browserbase in .env; the session page shows the Live View panel
#   once the application node opens the cloud browser.
```

## Files of note

- `backend/shared/application_rules.py`, `backend/browser/tools/form_filler.py`, `backend/browser/tools/appliers/base.py`
- `backend/browser/fetch_verifier.py`, `backend/orchestrator/agents/scoring.py`
- `backend/browser/browserbase_client.py`, `backend/browser/login_capture.py`, `backend/shared/browserbase_store.py`,
  `backend/gateway/routes/browserbase.py`
- `backend/browser/tools/appliers/indeed.py`, `backend/browser/tools/ats_detector.py`
- `frontend/src/lib/liveView.ts`, `frontend/src/components/LiveBrowserPanel.tsx`,
  `frontend/src/app/(session)/session/[id]/page.tsx`, `frontend/src/app/(dashboard)/settings/page.tsx`
- Tests: `backend/tests/test_application_rules.py`, `test_fetch_verifier.py`, `test_browserbase_settings.py`,
  `test_indeed_applier.py`, `conftest.py`; `frontend/src/lib/liveView.test.ts`
