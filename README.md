# JobHunter Agent — AI-Powered Autonomous Job Application Platform

An open-source AI agent that discovers jobs, scores them against your resume, tailors applications, and submits them autonomously — with a live browser feed so you can watch and intervene in real time.

**Built with:** FastAPI + LangGraph (Python) | Next.js 15 | Browserbase + Stagehand (Indeed demo) | Skyvern + Bright Data MCP (alternative paths) | EvoAgentX (prompt optimization)

**Live at:** [jobhunteragent.com](https://jobhunteragent.com)

---

## Indeed demo: Browserbase + Stagehand

This path discovers jobs on Indeed and uses [Stagehand](https://docs.stagehand.dev/v4) to operate a real [Browserbase](https://www.browserbase.com/) browser. JobHunter owns the workflow, applicant facts, limits, and submission checks. Stagehand handles page interpretation and browser controls; it needs the instructions and application logic in this repository.

After the [Quick Start](#quick-start), configure the backend for the demo:

```bash
INDEED_ONLY=true
BROWSER_MODE=browserbase
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
BROWSERBASE_API_KEY=...
BROWSERBASE_PROJECT_ID=...
BROWSERBASE_PROXIES=true
```

Sign in with Google, then open **Settings**. Public visitors supply their own Anthropic API key and Browserbase API key/project; keys are encrypted and never returned in full. Complete the Indeed login capture before applying. Application sessions reuse that user's persisted Browserbase Context. Server-funded model/browser credentials and contexts are available only to the explicit `BROWSERBASE_CONTEXT_USER_ID` owner. Missing visitor keys block model work without falling back to the owner's account. Browserbase login and the app's Google login are separate.

Settings shows the effective model IDs and, for the demo owner only, the model budget's settled charges, held reservations, and remaining allowance. Opening a saved résumé does not start an AI request; résumé analysis is an explicit action and matching cached analysis is reused.

Upload the original resume and save application rules, then describe the roles, location, work arrangement, and salary preferences in the UI. For the initial end-to-end check, use **Quick Apply with one Indeed URL** and aim for **one verified submission**. Quick Apply processes its supplied URLs; discovery sessions can backfill eligible jobs toward a configured submission target.

The application flow is:

1. **Discover and queue.** Search Indeed, score eligible jobs, and process native applications. With `INDEED_EASY_APPLY_ONLY=true`, employer-site redirects and nested employer sign-ins are skipped. The separate employer application queue is available only outside that policy.
2. **Operate the browser.** Stagehand uses `extract` / `observe` / `act`, native locators, original-file upload, and iframe-aware snapshots. Browserbase reuses authentication and manages supported CAPTCHAs. The app waits on solving events and rechecks the page; a finished event alone does not prove readiness.
3. **Ground answers.** An independent LLM judge uses the uploaded resume, profile, and explicit owner rules. It can synthesize supported experience and dates, with one bounded correction opportunity and source quotations. It must not invent credentials or personal facts.
4. **Queue unknowns in the app.** **Needs your answer** displays the exact unresolved question while other eligible jobs continue. Saving an answer does not restart the run; the UI offers an explicit retry. API/SSE consumers receive the same question state.
5. **Verify submission.** Final review is audited before a durable submission intent is recorded. Only a current confirmation with no remaining submit button counts as submitted. An uncertain outcome remains held for reconciliation instead of being automatically submitted again.

### Local demo spending guard

`JOBHUNTER_MODEL_BUDGET_LEDGER` is an opt-in **backend process environment variable** pointing to an absolute, initialized SQLite ledger. Initialize it once with `Ledger.create(path, limit_usd=...)` from `backend.shared.model_budget`, then export the path before starting the backend. Merely adding it to the Settings model or assuming the local value exists on Railway does not enable it. Existing ledgers must not be replaced to reset spend; missing or corrupt configured ledgers block paid model calls.

This guard supports the approved Anthropic model path and requires persistent storage across restarts. It does **not** cap Browserbase browser time/proxy traffic or requests made by other processes. Without the variable, this local model-spend ceiling is not active.

### Models

Defaults verified against the provider catalogs on October 4, 2026:

| Workload | Anthropic | Optional OpenAI provider |
| --- | --- | --- |
| Main workflow and browser | Sonnet 5.5 | GPT-6 Luna |
| Premium resume tailoring | Opus 5.5 | GPT-6 Astra |
| Lightweight checks and reports | Haiku 4.5 | GPT-6 Luna |
| Alternate browser-use path | Haiku 4.5 | GPT-6 Luna |

The budgeted demo pins all requests through its shared model factory, including Stagehand's model callback, answer judging, and cover-letter generation, to **Sonnet 5.5**. It reserves the model's full 1M input bound plus the configured output maximum at $2/$10 per million tokens; an 8,192-output call reserves $2.081920 before dispatch. Existing charges and unresolved reservations are never repriced by a model upgrade. Browserbase runs the browser; the application pays for inference through its own model client.

Explicit model environment variables override the regular defaults, so update those on Railway and in local `.env` files when upgrading. Budget mode uses its own reviewed model pin. Sonnet/Opus 5.5 use native JSON structured responses and omit unsupported temperature settings. The optional OpenAI shared client uses Responses for GPT-6 tools; the alternate browser-use client uses GPT-6 Luna's supported non-reasoning Chat Completions path. The alternate Anthropic browser-use client uses current Haiku because its forced-tool protocol is incompatible with Sonnet/Opus 5.5; the Indeed demo uses Stagehand with Sonnet 5.5.

Sources: [Anthropic models](https://platform.claude.com/docs/en/models/overview), [Sonnet 5.5 limits and pricing](https://platform.claude.com/docs/en/models/sonnet-5-5/overview), [OpenAI models](https://developers.openai.com/api/docs/models), [GPT-6 migration guide](https://developers.openai.com/api/docs/guides/latest-model).

---

## How It Works

The alternative multi-board workflow remains available; the Indeed demo above uses its dedicated Browserbase/Stagehand path.

```
You provide: keywords, resume, preferences
                    ↓
8-Agent LangGraph Pipeline:
  1. Intake        → parses your input into structured config
  2. Career Coach  → rewrites resume, scores it, generates cover letter template
  3. [YOU REVIEW]  → approve coached resume before proceeding
  4. Discovery     → searches ATS platforms via Bright Data MCP + Greenhouse API
  5. Scoring       → ranks jobs 0-100 against your profile (batch LLM calls)
  6. Resume Tailor → per-job resume adaptation
  7. [YOU REVIEW]  → approve shortlist before applying
  8. Application   → Skyvern fills forms on Greenhouse, Lever, Ashby, Workday
  9. Verification  → screenshots confirmation pages
  10. Reporting    → session summary + AI-generated next steps
                    ↓
Self-improvement: EvoAgentX optimizes prompts based on session outcomes
```

---

## Key Features

- **Agentic job discovery** — LLM generates search queries targeting ATS platforms (Greenhouse, Lever, Ashby, Workday) via Bright Data MCP. No auth-walled scraping.
- **AI form filling** — Skyvern (visual AI) handles complex ATS application forms including file uploads, dropdowns, and multi-step flows.
- **Self-improving prompts** — EvoAgentX TextGrad automatically optimizes discovery and scoring prompts based on real session outcomes. The agent gets smarter over time.
- **HITL checkpoints** — Two interrupt gates let you review the coached resume and approve the shortlist before any applications are submitted.
- **Real-time SSE streaming** — Watch every step live: discovery progress, scoring results, application status, browser actions.
- **Resume encryption** — Fernet (AES-128-CBC + HMAC) encryption at rest, persisted to Postgres (not ephemeral /tmp).
- **Session recovery** — LangGraph checkpoints to Postgres. Sessions survive backend restarts.
- **Credit-based billing** — Stripe integration with credit packs and unlimited monthly plans.

---

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────┐
│  Next.js 15 │     │ FastAPI (port 8000)                  │
│  (port 3000)│────►│                                      │
│             │     │  ├── API Routes (REST + SSE)          │
│  App Router │◄────│  ├── LangGraph Pipeline (8 agents)   │
│  NextAuth   │ SSE │  ├── Skyvern Client (form filling)   │
│  shadcn/ui  │     │  ├── MCP Client (Bright Data)        │
│  Formik     │     │  ├── EvoAgentX (prompt optimization) │
│             │     │  └── Event Bus (Redis pub/sub)        │
└─────────────┘     └──────────┬────────────┬──────────────┘
                               │            │
                          ┌────▼────┐  ┌────▼────┐
                          │Postgres │  │  Redis  │
                          │ :5433   │  │  :6379  │
                          └─────────┘  └─────────┘
```

---

## Quick Start

### Prerequisites
- Python 3.11 or 3.12 (CI runs both; the Docker image uses 3.11)
- Node.js 20+
- Docker (for Postgres + Redis)

### Setup

```bash
# Clone
git clone https://github.com/youngfreezy/job-hunter-agent.git
cd job-hunter-agent

# Environment
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, NEXTAUTH_SECRET, DATABASE_URL, REDIS_URL

# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install

# Start everything (Docker + backend + frontend)
cd ..
npm start
```

Open [http://localhost:3000](http://localhost:3000).

### Tests

```bash
# Backend (from the repo root; Postgres-backed tests skip with a reason when no DB is up)
python -m pytest backend/tests -q

# Frontend unit tests, lint, typecheck, production build
cd frontend && npm test && npx next lint && npx tsc --noEmit && npm run build
```

### Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-xxx        # Claude API key
DATABASE_URL=postgresql://...       # Postgres connection
REDIS_URL=redis://localhost:6379    # Redis connection
NEXTAUTH_SECRET=xxx                 # Auth session secret
NEXTAUTH_URL=http://localhost:3000  # Auth base URL

# Optional
SKYVERN_API_URL=http://localhost:8080/api/v1  # Skyvern instance
SKYVERN_API_KEY=xxx                           # Skyvern auth
BRIGHT_DATA_MCP_TOKEN=xxx                     # Bright Data MCP token
EVOAGENTX_ENABLED=true                        # Self-improvement loop
```

---

## Self-Improving Agent Loop

JobHunter uses [EvoAgentX](https://github.com/EvoAgentX/EvoAgentX) to automatically improve its prompts over time:

1. **Every session outcome is logged** — discovery count, success/failure rates, error categories, ATS breakdown
2. **Every 10 sessions**, TextGrad optimization runs automatically
3. **Optimized prompts are saved** to a versioned Postgres registry with rollback support
4. **Next session loads the best prompts** — discovery queries, scoring criteria, etc.

What gets optimized:
- Discovery search query generation (which queries find apply-able jobs?)
- Job scoring prompts (which criteria predict successful applications?)

Cost: ~$0.50-1.00 per optimization run (Haiku for execution, Sonnet for optimization).

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI + LangGraph (Python 3.11) |
| Frontend | Next.js 15 + Tailwind + shadcn/ui |
| Form Filling | Stagehand on Browserbase for the Indeed demo; Skyvern for alternative paths |
| Job Discovery | Indeed browser discovery; Bright Data MCP + Greenhouse API for alternative paths |
| Prompt Optimization | EvoAgentX (TextGrad) |
| Database | PostgreSQL |
| Cache/Queue | Redis |
| Auth | NextAuth.js + JWT + CSRF double-submit |
| Encryption | Fernet (AES-128-CBC + HMAC) |
| Payments | Stripe (credit packs + subscriptions) |
| Deployment | Railway |

---

## Project Structure

```
job-hunter-agent/
├── backend/
│   ├── gateway/              # FastAPI app, routes, middleware
│   │   ├── main.py
│   │   ├── routes/           # sessions, auth, payments, health
│   │   └── middleware/       # CSRF, rate limiting, auth
│   ├── orchestrator/
│   │   ├── pipeline/         # LangGraph graph + state
│   │   └── agents/           # 8 agents (intake → reporting)
│   ├── browser/
│   │   └── tools/
│   │       ├── mcp_client.py        # Bright Data MCP client
│   │       ├── mcp_discovery.py     # MCP-based job discovery
│   │       ├── skyvern_applier.py   # Skyvern form filling
│   │       └── job_boards/          # Greenhouse API, etc.
│   ├── optimization/
│   │   └── evolve.py         # EvoAgentX TextGrad runner
│   └── shared/
│       ├── prompt_registry.py  # Versioned prompt storage
│       ├── outcome_store.py    # Session outcome tracking
│       ├── resume_store.py     # Encrypted resume persistence
│       ├── resume_crypto.py    # Fernet encryption
│       ├── config.py, llm.py, db.py
│       └── redis_client.py, event_bus.py
├── frontend/
│   └── src/app/              # Next.js 15 App Router
├── docker-compose.yml
├── package.json              # npm start orchestrates everything
└── CLAUDE.md                 # AI coding instructions
```

---

## Pricing

Credit-based pricing with Stripe:

| Pack | Price | Per Credit |
|------|-------|-----------|
| 5 credits | $12.99 | $2.60 |
| 10 credits | $24.99 | $2.50 |
| 25 credits | $54.99 | $2.20 |
| 50 credits | $99.99 | $2.00 |
| 100 credits | $179.99 | $1.80 |
| Unlimited monthly | $149.99/mo | — |

1 credit = 1 application submitted. 3 free credits for new users.

---

## Known Issues & Help Wanted

See [TECHNICAL_STRUGGLES.md](TECHNICAL_STRUGGLES.md) for a detailed breakdown of current challenges:

- Near-zero end-to-end success rate (auth walls, bot detection)
- Skyvern cost optimization ($50/day → switched to Haiku)
- Ephemeral filesystem issues on Railway
- Circuit breaker and error categorization gaps
- Self-improvement loop integration (in progress)

**Contributions welcome!** If you have experience with ATS form automation, self-improving agents, or Railway deployment patterns, we'd love your help.

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run tests: `cd frontend && npx playwright test`
5. Push and open a PR

---

## License

Copyright (c) 2026 V2 Software LLC. All rights reserved.

## Indeed + Browserbase interview demo

Set these in the root `.env` (both services now read it):

```dotenv
BROWSER_MODE=browserbase
INDEED_ONLY=true
BROWSERBASE_API_KEY=<your key>
BROWSERBASE_PROJECT_ID=<your project>
BROWSERBASE_PROXIES=true
NEXTAUTH_SECRET=<random secret>
NEXTAUTH_URL=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000
# Choose the provider matching your API key:
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<your key>
```

Use Google OAuth with `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`, or enable
password-protected local sign-in for `npm start`:

```dotenv
ENABLE_CREDENTIALS_AUTH=true
LOCAL_DEMO_EMAIL=<local demo account email>
LOCAL_DEMO_PASSWORD=<random password, at least 16 characters>
```

Google sign-in requests identity scopes by default. Gmail code reading is optional
(`ENABLE_GMAIL_VERIFICATION=true`) and requires Google consent.

Local sign-in is disabled in production. Application contact details come from
your resume, not the demo account email. `npm start` starts Postgres and Redis,
applies migrations, and starts both services. Backend reload is opt-in with
`BACKEND_RELOAD=true`; leave it off for an uninterrupted demo. Optional Skyvern and analytics
containers are not needed for this demo. Use a fresh local database for a fresh
install; an older database initialized outside Alembic may need schema reconciliation.

1. Open `http://localhost:3000/auth/login` and sign in.
2. In **Settings → Browserbase**, save the API key and project ID if they are not
   configured on the server. Click **Sign in to Indeed** and log in using the
   live browser. Alternatively, configure an existing logged-in Context using
   `BROWSERBASE_CONTEXT_IDS=indeed=<context-id>` together with
   `BROWSERBASE_CONTEXT_USER_ID=<your account UUID>`. Prefer saving it in your
   account Settings on production. This is a cloud browser login;
   it does not automatically inherit cookies from your desktop Chrome.
3. Open **New Session** and enter this in **Describe your job search**:

   > Find applied AI and AI-native software engineering positions in San Francisco
   > that are hybrid or remote. Exclude AI trainer, data annotation, and
   > non-software engineering roles.

4. Upload your real resume. Choose 5, 10, 15, or 20 applications, review the inferred keywords and launch. The prompt
   takes priority over resume-derived search preferences. Do not select
   **Remote only** if you also want hybrid roles.
5. Choose **Use Original & Discover Jobs** to preserve your uploaded resume,
   or approve the coached version. Review the shortlist, and approve only the jobs you want
   submitted. Watch the Browserbase live view during discovery and applications.

With `INDEED_ONLY=true`, the server forces Indeed discovery, reuses the same
Indeed Context for applications, disables direct ATS API submission, and blocks
navigation outside HTTPS Indeed domains. Jobs that require an employer's
external application site cannot complete in this mode. An expired login,
CAPTCHA, or unsupported form can still stop a run; a successful submission must
have a confirmation page, not merely a click on Apply.

Indeed applications use [Stagehand v4](https://docs.stagehand.dev/), Browserbase's
AI SDK, to read each page and act on natural-language instructions. The application
flow does not depend on hard-coded Indeed wizard selectors. The original uploaded
resume is transferred from encrypted storage, required unknown answers stop for
review, and an independent check of the Indeed receipt determines success. Each
application is limited to 40 actions and 10 minutes. An uncertain submission is
never automatically retried; check Indeed before starting another attempt.

For the temporary interview explainer, set `NEXT_PUBLIC_BROWSERBASE_DEMO=true`
on the frontend **before building**. Set it to `false` and rebuild after the demo.
The links are ordinary product/documentation links, not referral links.

No special prompt phrase is required to select Browserbase or preserve auth.
Those are configuration and code constraints. The prompt controls what jobs to
find and how to rank them. Inspect the shortlist because job-board metadata can
be incomplete, especially work arrangement and location.

For verification, run the backend suite against a dedicated test database, then
run `npm test`, `npm run lint`, and `npm run build` from `frontend`. Development
uses `.next-dev` so a production build cannot overwrite a running demo's assets.
