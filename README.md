# JobHunter Agent — Autonomous Job Application Platform

## Current Status

This repository contains both implemented code and forward-looking design notes. The authoritative live-verified status is tracked in [docs/live-verification.md](docs/live-verification.md).

**Live-verified on March 6, 2026:** the core session flow is working end-to-end with real backend calls and real browser automation. Verified flows include session creation, coaching review, shortlist review, manual intervention resume, LLM-backed session steering, screenshot streaming, browser takeover through the UI, and manual-apply log persistence for submitted jobs with cover letter plus tailored resume.

**What works today:**
- 3-step session wizard (keywords, resume upload, review) with form persistence
- 8-agent LangGraph pipeline: Intake -> Coach -> Discovery -> Scoring -> Tailor -> Apply -> Verify -> Report
- 2 HITL gates: coach review + shortlist approval
- Job discovery across LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google Jobs, Greenhouse
- ATS-aware application: dedicated appliers for LinkedIn, Indeed, Glassdoor, ZipRecruiter, Greenhouse, Lever, Workday, Ashby + generic fallback
- Selector learning: both discovery and apply selectors stored in Postgres, ranked by success rate
- Daily automated health-check validates all CSS selectors against live pages
- Application results persisted to Postgres with full audit trail
- SSE + WebSocket real-time updates, screenshot streaming, and UI takeover relay
- NextAuth authentication, manual apply page, session rewind via checkpoints

**Important caveats:**
- The runtime takeover path currently proven on macOS is the in-app screenshot/input relay. The older noVNC/X11 scaffold exists but is not the verified production path.
- The session steering chat is backed by an LLM judge at the control layer. It is not yet a first-class LangGraph supervisor node.
- Interactive coaching chat is not yet implemented as a live collaborative editing loop.

**Not yet implemented:** Stripe payments, full standalone OSS packaging, production deployment, US-only geofencing, resume encryption.

See [docs/PLAN.md](docs/PLAN.md) for detailed implementation phases.
Startup can be launched from `./scripts/start-app.sh` or the macOS app bundle `JobHunter Agent.app`. See [docs/startup-packaging-plan.md](docs/startup-packaging-plan.md) for the remaining launcher packaging work.
Bright Data Browser can be enabled as an optional remote-browser backend for hostile ATS boards; see [docs/brightdata-routing.md](docs/brightdata-routing.md).

---

## Context
Job hunting is tedious and time-consuming regardless of role or industry. This platform creates a **keyword-driven, industry-agnostic** multi-agent system that discovers, scores, and applies to jobs autonomously — with a **live steerable video feed** so the user can watch and intervene in real-time. The user provides their own keywords (e.g., "Nurse Practitioner", "Data Engineer", "Marketing Manager", "Plumber"), resume, and preferences — the agent handles the rest.

Architecture uses LangGraph for agent orchestration with parallel fan-out, SSE streaming, AsyncPostgresSaver for HITL checkpointing, and a Next.js 14 frontend.

---

## Market Landscape

**Existing tools**: LazyApply ($99-249/mo), Sonara ($20-80/mo), JobCopilot ($24-32/mo), Simplify Copilot (free-$30/mo). All are self-serve Chrome extensions or basic auto-apply bots. None offer live video steering or real-time HITL.

**Open-source references**: ApplyPilot (Playwright + Claude), Browser-Use (78K+ stars, LLM-driven Playwright -- **integrated as our application engine**), Skyvern (computer vision + Playwright, 85.85% form-fill accuracy).

**Our differentiator**: live-steerable browser sessions with real automation, HITL recovery, and an in-app takeover path that has been verified end-to-end. Industry/keyword agnostic. AI-driven browser automation dynamically handles multiple ATS families without relying only on brittle hardcoded selectors.

---

## Agent Architecture (8 Agents)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          LangGraph StateGraph                            │
│                                                                          │
│  START                                                                   │
│    ↓                                                                     │
│  [1. INTAKE AGENT] ← User keywords, resume, preferences                 │
│    ↓                                                                     │
│  [2. CAREER COACH AGENT] ← Analyzes resume, LinkedIn, experience gaps   │
│    │  • Scores resume quality (0-100)                                    │
│    │  • Rewrites resume as a "personal salesperson"                      │
│    │  • Suggests LinkedIn profile improvements                           │
│    │  • Coaches on impostor syndrome / positioning                       │
│    │  • Generates master cover letter template                           │
│    │                                                                     │
│    ├── interrupt() → HITL: User reviews coached resume + advice          │
│    ↓                                                                     │
│  [3. DISCOVERY AGENT] ← Fan-out: Indeed, LinkedIn, Glassdoor,           │
│    │                     ZipRecruiter, Google Jobs (parallel Send)        │
│    ↓                                                                     │
│  [4. SCORING AGENT] ← Ranks jobs 0-100 vs coached profile               │
│    ↓                                                                     │
│  [5. RESUME TAILOR] ← Per-job resume adaptation from coached base        │
│    │                                                                     │
│    ├── interrupt() → HITL: User reviews shortlist + tailored resumes     │
│    ↓                                                                     │
│  [6. APPLICATION AGENT] ← Playwright: forms, uploads, cover letters      │
│    │                       Per-application subtasks via ARQ queue         │
│    │                       ↕ Live tiered viewing + chat steering          │
│    │                                                                     │
│    ├── interrupt() → HITL: Obstacle pause (CAPTCHA, 2FA, ambiguity)      │
│    ↓                                                                     │
│  [7. VERIFICATION AGENT] ← Screenshots proof, confirms submission        │
│    ↓                                                                     │
│  [8. REPORTING AGENT] ← Session summary, metrics, next steps             │
│    ↓                                                                     │
│  END                                                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

### Agent Breakdown

| # | Agent | Model | Purpose |
|---|-------|-------|---------|
| 1 | **Intake** | Sonnet 4.6 | Parses keywords, resume, preferences → structured `SearchConfig` |
| 2 | **Career Coach** | Opus 4.6 | **The user's personal salesperson.** Analyzes resume + LinkedIn profile. Identifies strengths the user undervalues (combats impostor syndrome). Rewrites resume to "sell" the person — not just list experience. Generates a master cover letter template. Advises on LinkedIn headline/about/skills. Scores resume 0-100 with actionable improvement feedback. |
| 3 | **Discovery** | Sonnet 4.6 + Playwright | Concurrent job board scraping via `asyncio.gather()`. All boards (Indeed, LinkedIn, Glassdoor, ZipRecruiter) scraped in parallel with isolated BrowserContexts sharing one Chromium process. |
| 4 | **Scoring** | Sonnet 4.6 | Scores each job 0-100 against the **coached** profile (not raw resume). Deduplicates. Batches scored concurrently (10 parallel LLM calls). |
| 5 | **Resume Tailor** | Sonnet 4.6 (default) / Opus 4.6 (top 20%) | Per-job adaptation from the coached base resume. 10 concurrent LLM calls. Self-reflection retry only for top-20% jobs. |
| 6 | **Application** | Sonnet 4.5 + browser-use | Core agent. Uses [browser-use](https://github.com/browser-use/browser-use) (LLM-driven browser automation) to dynamically navigate application forms, click buttons, fill fields, and submit -- no hardcoded CSS selectors. Handles LinkedIn Easy Apply, Workday, Greenhouse, and any ATS. Live-steerable. |
| 7 | **Verification** | Haiku 4.5 | Screenshots confirmation pages, verifies submission success. |
| 8 | **Reporting** | Haiku 4.5 | Session summary with metrics, callback predictions, coach follow-up tips. |

**The runtime now defaults to OpenAI models.** The shared LLM layer supports OpenAI-first routing with Anthropic as an explicit fallback provider.

### Career Coach Agent — Deep Dive

The Coach is the **emotional and strategic heart** of the product. It's what turns this from "another auto-apply bot" into a premium career service.

**What it does:**

1. **Resume Analysis & Rewrite**
   - Reads the raw resume and identifies: undersold skills, missing keywords, weak action verbs, formatting issues
   - Rewrites as a salesperson would pitch this person — confident, specific, outcome-driven
   - "You didn't just 'help with deployments' — you 'architected CI/CD pipelines that reduced deployment time by 40%'"

2. **Impostor Syndrome Coaching**
   - Detects hedging language ("helped with", "assisted in", "was part of")
   - Replaces with ownership language ("led", "designed", "delivered")
   - Provides an encouraging message: "Based on your experience, you're qualified for Senior-level roles. Here's why..."
   - Frames career gaps or transitions positively

3. **LinkedIn Profile Advice**
   - User optionally provides their LinkedIn URL
   - Agent scrapes profile (via Playwright) and compares to the resume
   - Suggests: headline rewrite, about section, featured skills, missing endorsements
   - Output: actionable bullet-point list of LinkedIn improvements

4. **Master Cover Letter Template**
   - Generates a base cover letter that captures the user's voice and story
   - Template has [COMPANY], [ROLE], [SPECIFIC_REASON] placeholders
   - The Application Agent fills these per job — but the voice stays consistent

5. **Resume Score (0-100)**
   - Scored against: keyword density for target roles, quantified achievements, formatting, ATS compatibility, readability
   - Shown to user with breakdown: "Keywords: 72/100, Impact Metrics: 45/100, ATS Compatibility: 88/100"

6. **Coaching Review Gate**
   - The current product exposes coaching as a review/approval step, not as a live conversational editing session
   - The coached resume and feedback stream to the UI, then the user approves before discovery starts
   - Conversational coaching remains planned work rather than a live-verified feature

### Cost Per Session (Historical Claude Estimate)

| Agent | Calls/Session | Cost/Call | Total |
|-------|--------------|-----------|-------|
| Intake | 1 | $0.03 | $0.03 |
| Career Coach (Opus) | 3-5 (resume + LinkedIn + cover letter + scoring) | $0.25 | $0.75-1.25 |
| Discovery | 50-100 | $0.015 | $0.75-1.50 |
| Scoring | 200 | $0.02 | $4.00 |
| Resume Tailor (Sonnet 80%) | 160 | $0.02 | $3.20 |
| Resume Tailor (Opus 20%) | 40 | $0.18 | $7.20 |
| Application (Opus) | 100-200 | $0.14 | $14-28 |
| Verification | 100-200 | $0.002 | $0.20-0.40 |
| Reporting | 1 | $0.01 | $0.01 |
| **Total** | | | **$30-46** |

---

## Live Steering

### SSE Status Feed

All plans include real-time SSE text updates that stream agent progress:
- "Searching LinkedIn for 'Data Engineer'..."
- "Scoring 47 jobs against your profile..."
- "AI agent applying to Senior Engineer at Stripe... filling education field... submitted!"

The frontend receives granular SSE events from each agent phase (discovery_progress, scoring_progress, tailoring_progress, application_progress, application_browser_action) with step-by-step detail.

### Chat Steering

Users can steer the live session through the chat panel during runtime:
- The current implementation uses an LLM judge over recent session state and event context
- Verified directives include workflow guidance such as pause/resume/skip-oriented control and takeover escalation
- This is not yet the same thing as a fully conversational coach/editor that rewrites artifacts inline during the coach step

---

## System Architecture

**Current architecture**: Single-service monolith for development simplicity. All components (API, LangGraph pipeline, browser automation) run in one FastAPI process.

```
┌─────────────┐     ┌──────────────────────────────────────┐
│  Next.js 14 │     │ FastAPI (port 8000)                  │
│  (port 3000)│────►│                                      │
│             │     │  ├── API Routes (REST + SSE + WS)    │
│  App Router │◄────│  ├── LangGraph Pipeline              │
│  NextAuth   │ SSE │  │   └── 8 agents (StateGraph)       │
│  shadcn/ui  │     │  ├── Browser Manager (Patchright)    │
│  Formik     │     │  ├── Selector Health Scheduler       │
│             │     │  └── Event Bus (pub/sub)             │
└─────────────┘     └──────────┬────────────┬──────────────┘
                               │            │
                          ┌────▼────┐  ┌────▼────┐
                          │Postgres │  │  Redis  │
                          │ :5433   │  │  :6379  │
                          └─────────┘  └─────────┘
```

**How a session runs:**

```
User clicks "Start Job Hunt Session"
  ↓
POST /api/sessions → starts LangGraph pipeline (async)
  ↓
Pipeline executes 9 nodes sequentially:
  1. Intake        → parse keywords + resume (Claude Sonnet)
  2. Career Coach  → rewrite resume, score, cover letter template (Claude Opus)
  3. [HITL Gate]   → interrupt() → user reviews coached resume
  4. Discovery     → fan-out to 7 job boards (Patchright + stealth)
  5. Scoring       → rank jobs 0-100 vs profile (10 concurrent Claude calls)
  6. Resume Tailor → per-job resume adaptation (10 concurrent Claude calls)
  7. [HITL Gate]   → interrupt() → user approves shortlist
  8. Application   → submit via ATS-specific appliers (circuit breaker at 3 failures)
  9. Verification  → screenshot + confirmation check
  10. Reporting    → session summary
  ↓
Each node publishes SSE events → Redis pub/sub → frontend StatusFeed
Pipeline state checkpointed to Postgres after each node (rewindable)
```

**Production target**: Split into API Gateway + Browser Workers (Railway) for isolation. Inngest for step-level retry. See [docs/PLAN.md](docs/PLAN.md) for the planned microservice architecture.

---

## State Schema (LangGraph)

```python
class JobHunterState(TypedDict):
    # Session identity
    session_id: str
    user_id: str
    created_at: str

    # User inputs (keyword-driven, industry-agnostic)
    keywords: List[str]                          # e.g. ["React", "Senior", "Remote"]
    locations: List[str]                         # e.g. ["San Francisco", "Remote"]
    remote_only: bool
    salary_min: Optional[int]
    resume_text: str
    resume_file_path: Optional[str]
    preferences: Dict[str, Any]                  # job type, company size, experience level

    # Discovery results
    discovered_jobs: Annotated[List[JobListing], operator.add]

    # Scoring results
    scored_jobs: List[ScoredJob]                 # sorted by fit score desc

    # Resume tailoring
    tailored_resumes: Dict[str, TailoredResume]  # job_id → tailored resume
    resume_scores: Dict[str, int]                # job_id → fit score (0-100)

    # Application progress
    application_queue: List[str]                 # job_ids approved for application
    current_application: Optional[str]
    applications_submitted: Annotated[List[ApplicationResult], operator.add]
    applications_failed: Annotated[List[ApplicationResult], operator.add]
    applications_skipped: Annotated[List[str], operator.add]

    # Browser state (for screenshot feed)
    browser_session_id: Optional[str]
    current_page_url: Optional[str]

    # HITL
    status: Literal["intake", "discovering", "scoring", "tailoring",
                     "awaiting_review", "applying", "paused",
                     "takeover", "completed", "failed"]
    human_messages: Annotated[List[HumanMessage], operator.add]
    steering_mode: Literal["status", "screenshot", "takeover"]

    # LangGraph messages
    messages: Annotated[List[BaseMessage], add_messages]

    # Errors + circuit breaker
    errors: Annotated[List[str], operator.add]
    consecutive_failures: int                    # reset on success, pause at 3

    # Billing
    session_start_time: Optional[str]
    applications_used: int                       # tracked against plan limit
```

---

## Tech Stack

### Backend (Implemented)
- **Python 3.11** + **FastAPI** (single service, port 8000, async throughout)
- **LangGraph** for agent orchestration (9-node StateGraph with 2 HITL interrupt gates)
- **AsyncPostgresSaver** for pipeline checkpointing + session rewind
- **Patchright** for anti-detection browser automation (patched Playwright fork)
- **browser-use** for AI-driven form filling (fallback for unknown ATS platforms)
- **LLM provider** — OpenAI by default, Anthropic supported as an explicit fallback
- **PostgreSQL** (Docker, port 5433) — checkpoints, selector memory, application results
- **Redis** (Docker, port 6379) — pub/sub for SSE events, screenshot streaming, caching
- **Neo4j** client (optional, graceful degradation)

### Frontend (Implemented)
- **Next.js 14** (App Router, TypeScript, port 3000)
- **Tailwind CSS** + **shadcn/ui** component library
- **Formik + Yup** for multi-step forms with localStorage persistence
- **NextAuth.js** for authentication (email/password credentials)
- **nextjs-toploader** for route transitions
- **Playwright** for E2E testing (64 tests across 8 files)

### Infrastructure (Local Dev)
- **Docker Compose** — Postgres + Redis
- **npm start** from root — orchestrates Docker, backend (uvicorn --reload), frontend (next dev)

### Infrastructure (Planned for Production)
- **Vercel** — Frontend hosting
- **Railway** — Backend + Browser Workers
- **Neon** — Managed Postgres
- **Upstash** — Managed Redis
- **Stripe** — Payments (per-job pricing model)
- **Resend** — Transactional emails
- **Sentry** — Error tracking
- **BrightData / Oxylabs** — Residential proxy rotation

---

## Database Design

### Postgres — Currently Implemented
```sql
-- Discovery selector memory (learns which CSS selectors work per job board)
board_selectors (
  id SERIAL PK, board TEXT, selector TEXT,
  success_count INT, fail_count INT, last_used TIMESTAMPTZ,
  last_checked TIMESTAMPTZ, last_check_passed BOOLEAN,
  UNIQUE (board, selector)
)

-- Application selector memory (learns apply/next/submit selectors per ATS)
apply_selectors (
  id SERIAL PK, platform TEXT, step_type TEXT, selector TEXT,
  success_count INT, fail_count INT, last_used TIMESTAMPTZ,
  last_checked TIMESTAMPTZ, last_check_passed BOOLEAN,
  UNIQUE (platform, step_type, selector)
)

-- Persistent application results log
application_results (
  id SERIAL PK, session_id TEXT, job_id TEXT, status TEXT,
  job_title TEXT, job_company TEXT, job_url TEXT, job_board TEXT,
  error_message TEXT, cover_letter TEXT, tailored_resume_text TEXT,
  duration_seconds INT, created_at TIMESTAMPTZ
)

-- LangGraph checkpoint tables (auto-created by AsyncPostgresSaver)
checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations
```

### Postgres — Planned (Not Yet Implemented)
```sql
users, sessions, resumes (encrypted), stripe_events
```

### Neo4j — Knowledge Graph (Optional)
Client implemented in `shared/neo4j_client.py`. System degrades gracefully when Neo4j is unavailable — falls back to stateless form filling without cross-session learning.

---

## Pricing (Per-Job Model)

> Updated March 2026 — Switched from weekly subscriptions to per-job pricing.
> Full analysis in [docs/phase-4-5-monetization.md](docs/phase-4-5-monetization.md).

**$1.99 per successful application** — users only pay when an application is verified as submitted.

| Model | Price | Per Job | Discount |
|-------|-------|---------|----------|
| Pay-as-you-go | -- | $1.99 | -- |
| 20-pack | $29.99 | $1.50 | 25% off |
| 50-pack | $64.99 | $1.30 | 35% off |
| 100-pack | $119.99 | $1.20 | 40% off |

**Free tier:** 3 free applications to convert new users.

### Margin Analysis

Estimated LLM cost per job: ~$0.25-0.30. At $1.99/job = ~85% gross margin.

| Jobs/mo | Revenue | LLM Cost | Infra | Margin |
|---------|---------|----------|-------|--------|
| 500 (25 users) | $997 | $150 | $50 | 80% |
| 2,000 (100 users) | $3,980 | $600 | $150 | 81% |
| 10,000 (500 users) | $19,900 | $3,000 | $500 | 82% |

---

## TODO: US-Only Access

> Not yet implemented. Planned for production deployment.

### Geo-Restriction (Defense in Depth)
1. **Cloudflare WAF** — Firewall rule blocking all non-US traffic at CDN edge (free tier)
2. **NextAuth middleware** — Server-side IP check via MaxMind GeoLite2 DB on signup + session start
3. **Stripe** — Payment method restricted to US-issued cards
4. **Landing page** for non-US visitors: "Currently available in the United States only. Join the waitlist."

---

## Security & Data Privacy

> Most security features below are TODO — planned for production. Currently implemented: NextAuth session-based auth, auth middleware on protected routes, per-session browser isolation.

### TODO: Resume / PII Encryption
- Encrypt resumes at rest with `pgcrypto` AES-256 in Postgres
- Auto-delete resumes 30 days after last session unless user opts to retain
- Field-level encryption for name, email, phone, address
- "Delete my data" endpoint (CCPA/GDPR compliance)

### Job Board Credentials (Design Principle)
- **Never store passwords.** Use "bring your own session" model:
  - User logs into job boards during a Takeover phase
  - Agent uses those authenticated browser sessions (cookies only)
  - Encrypted cookie jar stored per user, separate from main DB

### TODO: Payment Security
- Stripe Checkout (hosted page) — zero PCI scope on our side
- Never store card details
- Idempotency keys on all Stripe webhook handlers

### TODO: Production Infrastructure Security
- Railway private networking between services
- Neon Postgres with enforced SSL + connection pooling
- Short-lived JWTs (15-min expiry) + refresh tokens
- Separate browser process per user (not shared BrowserContext) for session isolation
- Ephemeral `/tmp/{session_id}/` storage per session, cleaned up on completion

---

## Resilience & Error Handling

### Implemented
- **Circuit breaker**: Application Agent tracks `consecutive_failures` in LangGraph state. After 3 consecutive failures → pauses and alerts user.
- **Graceful degradation**: Neo4j down → stateless form filling. Board blocked → skip and continue. Redis drops → SSE auto-reconnects.
- **Selector self-healing**: Daily health-check validates CSS selectors against live pages. Broken selectors flagged, working ones prioritized by success rate.
- **Checkpoint persistence**: Pipeline state saved to Postgres after each node. Sessions can be rewound to any checkpoint.

### TODO
- **Per-application retry**: Independent subtasks with browser context crash recovery
- **LLM retry**: Exponential backoff with provider-aware retry handling

---

## TODO: Marketplace & Distribution

### Phase 1: Direct (Week 1-4)
- Own website with Stripe Checkout at custom domain
- **Upwork**: Premium service listing at $100/hr (done-for-you framing)
- **Fiverr**: "AI agent applies to 200+ jobs for you"

### Phase 2: Visibility (Month 2)
- **Product Hunt** launch
- **AI Agent Store** (aiagentstore.ai) + **AI Agents Directory**
- **Twitter/X**, **Reddit** (r/jobsearchhacks, r/cscareerquestions, r/recruitinghell)
- Blog content: "I let an AI apply to 200 jobs — here's what happened"

### Phase 3: Growth (Month 3+)
- Referral program ($25 credit per referral)
- Concurrent session support (multiple users simultaneously)
- Outcome-based pricing experiment: "Pay only for interviews booked"

---

## Project Structure

```
job-hunter-agent/
├── backend/
│   ├── gateway/
│   │   ├── main.py                     # FastAPI app, LangGraph setup, scheduler init
│   │   └── routes/
│   │       ├── auth.py                 # /me endpoint (NextAuth)
│   │       ├── health.py              # /api/health
│   │       ├── sessions.py            # Session CRUD, SSE, HITL endpoints
│   │       ├── selectors.py           # Selector status + health-check API
│   │       ├── payments.py            # Stripe webhook handling
│   │       └── ws.py                  # WebSocket /ws/sessions/{id}
│   ├── orchestrator/
│   │   ├── pipeline/
│   │   │   ├── graph.py               # LangGraph StateGraph (9 nodes + 2 HITL gates)
│   │   │   └── state.py               # JobHunterState TypedDict
│   │   └── agents/                    # 8 specialized agents
│   │       ├── intake.py, career_coach.py, discovery.py, scoring.py
│   │       ├── resume_tailor.py, application.py, verification.py, reporting.py
│   │       └── _login_sync.py
│   ├── browser/
│   │   ├── manager.py                 # BrowserManager lifecycle
│   │   ├── playwright_pilot/pilot.py  # Playwright API wrapper
│   │   ├── streaming/                 # Screenshot + VNC streaming
│   │   ├── tools/
│   │   │   ├── job_boards/            # 7 boards: linkedin, indeed, glassdoor,
│   │   │   │                          #   ziprecruiter, google_jobs, greenhouse_boards
│   │   │   ├── appliers/             # 9 ATS: linkedin, indeed, glassdoor,
│   │   │   │                          #   ziprecruiter, greenhouse, lever, workday, ashby, generic
│   │   │   ├── apply_selectors.py, ats_detector.py, browser_use_applier.py
│   │   │   ├── form_filler.py, cover_letter.py, linkedin_updater.py
│   │   │   └── direct_discovery.py, browser_use_discovery.py, account_creator.py
│   │   └── anti_detect/stealth.py
│   ├── shared/
│   │   ├── models/schemas.py          # 23+ Pydantic models
│   │   ├── application_store.py       # application_results table
│   │   ├── selector_memory.py         # board_selectors table + health-check
│   │   ├── selector_health.py         # Unified health-check runner
│   │   ├── scheduler.py              # Async periodic scheduler (daily checks)
│   │   ├── config.py, event_bus.py, llm.py
│   │   ├── neo4j_client.py, redis_client.py
│   │   └── patches.py
│   ├── docker-compose.yml, requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/                       # Next.js 14 App Router
│   │   │   ├── page.tsx, layout.tsx, loading.tsx
│   │   │   ├── auth/login/ + signup/
│   │   │   ├── dashboard/page.tsx     # Session history
│   │   │   ├── session/new/page.tsx   # 3-step creation wizard
│   │   │   ├── session/[id]/page.tsx  # Live session viewer
│   │   │   └── session/[id]/manual-apply/page.tsx
│   │   ├── components/
│   │   │   ├── StatusFeed, ChatPanel, CoachPanel, JobCard
│   │   │   ├── forms/                # Formik form components
│   │   │   ├── wizard/               # Session wizard steps
│   │   │   └── ui/                   # shadcn/ui
│   │   ├── lib/
│   │   │   ├── api.ts, websocket.ts
│   │   │   ├── hooks/usePersistedFormik.ts
│   │   │   └── schemas/session.ts, auth.ts
│   │   └── middleware.ts             # Auth middleware
│   └── tests/e2e/                     # 8 Playwright test files (64 tests)
├── docs/
│   ├── PLAN.md                        # Implementation plan + phases
│   ├── phase-4-5-monetization.md      # Pricing analysis
│   └── diagrams/                      # Mermaid architecture diagrams
├── scripts/start.js                   # Orchestrates Docker + backend + frontend
├── package.json                       # npm start
├── CLAUDE.md                          # AI coding instructions
└── README.md                          # This file
```

---

## Implementation Status

See [docs/PLAN.md](docs/PLAN.md) for detailed phase tracking with checkboxes.

| Phase | Status | Highlights |
|-------|--------|------------|
| 1. Foundation | COMPLETED | 8 agents, LangGraph pipeline, SSE, Docker, npm start |
| 2. Browser Automation | COMPLETED | 7 board scrapers, 9 ATS appliers, anti-detect, selector memory |
| 3. Auth + SSE + UX | COMPLETED | NextAuth, wizard, HITL gates, manual apply, loading skeletons |
| 4. Persistence + Self-Healing | PARTIAL | Selector health checks, app results log, checkpoints. TODO: Stripe, session DB, encryption |
| 5. Deploy + Launch | NOT STARTED | TODO: Vercel, Railway, Neon, proxies |
| 6. Testing | IN PROGRESS | 64 E2E tests passing. TODO: pytest unit/integration tests |

---

## TODO: Scaling Roadmap

| Users | Infra | Monthly Cost | Changes Needed |
|-------|-------|-------------|----------------|
| 1-10 | 1 gateway, 1 orchestrator, 2 browser workers | ~$150 | None |
| 10-50 | 1 gateway, 2 orchestrators, 5 browser workers | ~$400 | Railway autoscaling |
| 50-100 | 2 gateways (load balanced), 3 orchestrators, 10 browser workers | ~$900 | Session-affine routing |
| 100-500 | Railway autoscaling across all services | ~$3,000 | Kubernetes evaluation |
| 500+ | Migrate to Kubernetes (EKS/GKE) | ~$8,000+ | Full K8s migration |

---

## Testing

### Implemented
- **E2E tests**: 64 Playwright tests across 8 files, all passing. Covers auth, landing page, session wizard, session viewer, dashboard persistence, pipeline flow, API health, and full end-to-end flow.

```bash
cd frontend && npx playwright test     # Run all E2E tests
```

### TODO
- **Unit tests**: Each agent in isolation with mocked LLM responses (pytest)
- **Integration tests**: Full pipeline with test job listings
- **Load test**: Concurrent WebSocket connections + session throughput
- **Billing test**: Stripe test mode — verify plan limits, cancellation
- **Security audit**: Resume encryption, credential handling, session isolation

---

## Agent Design Principles

These principles are baked into the architecture — not afterthoughts.

### 1. Decomposition of Complex AI Problems into Agent-Based Architecture
- 7 specialized agents, each with a single responsibility (intake, discovery, scoring, tailoring, application, verification, reporting)
- LangGraph StateGraph defines the DAG — agents are nodes, data flows through typed state
- Fan-out via `Send` API for parallel discovery across 5 job boards simultaneously
- Each agent is independently testable, swappable, and upgradable

### 2. Integrating Models, Tools, Memory, and Control Loops
- **Models**: OpenAI-first routing for default and premium tasks; Anthropic available as fallback
- **Tools**: Playwright browser actions, Neo4j queries, resume parsing, cover letter generation — all registered as callable tools
- **Memory**: Neo4j knowledge graph persists cross-session learning (ATS strategies, successful answers). LangGraph state + Postgres checkpoints provide within-session memory.
- **Control loops**: Each agent runs a think→act→observe loop. The Application Agent specifically runs: observe page → decide action → execute via Playwright → verify result → repeat

### 3. Multi-Agent and Multimodal Systems
- **Multi-agent**: 7 agents with typed state handoffs. Parallel execution where independent (discovery). Sequential where dependent (scoring needs discovery results).
- **Multimodal**: Application Agent processes visual page screenshots (CDP) + HTML DOM + text content. Verification Agent analyzes confirmation page screenshots with Claude vision.
- Cross-agent communication via LangGraph state reducers (`Annotated[List, operator.add]` for findings, custom `_merge_dicts` for statuses)

### 4. Iterative Reflection and Feedback for Performance
- **Resume Tailor** generates a tailored resume → scores it against the JD → if score < 70, regenerates with specific improvement instructions (self-reflection loop)
- **Application Agent** fills a form → takes screenshot → verifies fields are correctly populated → corrects if needed (visual verification loop)
- **Neo4j feedback loop**: After applications, track which strategies led to callbacks. Feed outcomes back into the knowledge graph. Over time, the system learns which answers and approaches work for which companies.
- **RAGAS-style evaluation**: Periodically evaluate cover letter quality (faithfulness to resume, relevance to JD) using an evaluation agent

### 5. Trade-offs: Autonomy vs Safety vs Scalability
- **Autonomy ↔ Safety**: Three steering modes (Watch → Chat → Takeover) let users dial autonomy up or down. Default is semi-autonomous with HITL checkpoints at shortlist review and obstacle detection. Circuit breaker pauses after 3 consecutive failures.
- **Autonomy ↔ Scalability**: Opus (high autonomy, expensive) reserved for critical tasks. Sonnet/Haiku (lower cost, scalable) for routine work. Smart model routing based on job score.
- **Safety ↔ Scalability**: Per-user browser process isolation is expensive but necessary. noVNC only on-demand. Credential-free design (cookie-only auth) reduces security surface.
- **Explicit safety rails**: Never submit an application without at least one HITL checkpoint. Never store passwords. Encrypt all PII. Auto-delete data after 30 days.

---

## Environment Variables

```bash
# Required
LLM_PROVIDER=openai                    # openai or anthropic
OPENAI_API_KEY=sk-proj-xxx             # default provider
ANTHROPIC_API_KEY=sk-ant-xxx           # only needed for anthropic fallback
DATABASE_URL=postgresql://...          # Postgres (default: localhost:5433)
REDIS_URL=redis://localhost:6379       # Redis
NEXTAUTH_SECRET=xxx                    # NextAuth session secret
NEXTAUTH_URL=http://localhost:3000     # NextAuth base URL

# Optional
NEO4J_URI=neo4j+s://xxx               # Knowledge graph (graceful degradation)
STRIPE_SECRET_KEY=sk_test_xxx          # TODO: Not yet integrated
BROWSER_HEADLESS=true                  # Run browser headless
BROWSER_MODE=patchright                # "patchright" or "cdp"
PROXY_URL=http://user:pass@proxy:22225 # Residential proxy for anti-detection
```

### TODO: Runtime Secret Management (Production)
- **Vercel**: Secrets stored in Vercel Environment Variables (encrypted at rest, per-environment)
- **Railway**: Secrets stored in Railway Variables (encrypted, per-service)
- **Pre-commit hook**: `detect-secrets` or `trufflehog` to scan for accidentally committed keys
- **Never log secrets**: Custom log formatter strips any string matching `sk-`, `whsec_`, `re_`, etc.

---

## Legal

- **V2 Software LLC** — already established, limits personal liability
- **Terms of Service**: Users acknowledge automated applications may violate job board ToS; users accept responsibility
- **Privacy Policy**: CCPA/GDPR compliant. Data retention policy. Right to deletion.
- **No guarantees** of interview/hire outcomes
- **Liability insurance** (E&O / Professional Liability) recommended
- **Disclaimer**: "This service assists with job applications. Results vary. Not affiliated with any job board or ATS platform."
