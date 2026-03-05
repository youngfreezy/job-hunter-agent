# JobHunter Agent — Autonomous Job Application Platform

## Context
Job hunting is tedious and time-consuming regardless of role or industry. This platform creates a **keyword-driven, industry-agnostic** multi-agent system that discovers, scores, and applies to jobs autonomously — with a **live steerable video feed** so the user can watch and intervene in real-time. The user provides their own keywords (e.g., "Nurse Practitioner", "Data Engineer", "Marketing Manager", "Plumber"), resume, and preferences — the agent handles the rest. Built as a **weekly subscription SaaS**, US users only.

Architecture is modeled after the mayo-clinic-validator's proven LangGraph patterns: parallel agent fan-out via Send API, SSE streaming, PostgresCheckpointer for HITL, and a Next.js frontend — but redesigned for multi-tenant scale with microservice separation, job queues, and tiered resource allocation.

---

## Market Landscape

**Existing tools**: LazyApply ($99-249/mo), Sonara ($20-80/mo), JobCopilot ($24-32/mo), Simplify Copilot (free-$30/mo). All are self-serve Chrome extensions or basic auto-apply bots. None offer live video steering or real-time HITL.

**Open-source references**: ApplyPilot (Playwright + Claude), Browser-Use (78K+ stars, LLM-driven Playwright -- **integrated as our application engine**), Skyvern (computer vision + Playwright, 85.85% form-fill accuracy).

**Our differentiator**: Live-steerable browser session with chat + noVNC takeover. Industry/keyword agnostic. Cross-session learning via knowledge graph. AI-driven browser automation (browser-use) that dynamically handles any ATS without hardcoded selectors. No existing product offers this combination.

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

**All agents use Claude (Anthropic SDK) exclusively.** Smart model routing: Opus for high-reasoning tasks (coaching, form filling, top-tier resume tailoring). Sonnet for mid-tier. Haiku for lightweight.

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

6. **Interactive Chat During Coaching**
   - The Career Coach is **conversational** — user can steer it via the chat panel throughout
   - "Actually, I led that project, not just assisted" → Coach updates the resume immediately
   - "I'm not sure I'm qualified for Senior roles" → Coach responds with evidence from their experience
   - "Can you make the cover letter more casual?" → Coach adjusts tone
   - "I also have a side project that..." → Coach incorporates it
   - This isn't a one-shot rewrite — it's a **collaborative editing session** between user and AI coach
   - Uses the same chat panel / WebSocket infrastructure as the Application Agent steering
   - Coach outputs stream in real-time (SSE) so the user sees the resume/letter being written live

### Cost Per Session (Claude API)

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

Users can steer the agent via the chat panel throughout the session:
- During coaching: "Actually, I led that project" -> Coach updates resume
- During application: "Skip this job" or "Use a more formal tone"

---

## System Architecture (Microservice Split)

**Critical design decision**: Split the monolith into 3 services to prevent browser crashes from taking down the API, and to scale browser workers independently.

```
┌─────────┐     ┌───────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Vercel  │     │ API Gateway   │     │ Orchestrator     │     │ Browser Workers  │
│ (Next.js│────►│ (FastAPI)     │────►│ (LangGraph +     │────►│ (Playwright +    │
│ frontend│     │               │     │  ARQ consumer)   │     │  browser-use)    │
│         │◄────│ Auth, Stripe, │◄────│                  │◄────│                  │
│         │ SSE │ SSE, REST     │Redis│ Agent pipeline   │Redis│ Per-user browser │
│         │     │               │pub/ │ Session mgmt     │pub/ │ contexts         │
│         │     │               │sub  │                  │sub  │                  │
└─────────┘     └───────┬───────┘     └────────┬─────────┘     └──────────────────┘
                        │                      │
                   ┌────▼────┐            ┌────▼────┐
                   │ Neon    │            │ Neo4j   │
                   │Postgres │            │ Aura    │
                   │         │            │         │
                   └─────────┘            └─────────┘
```

### Service Responsibilities

| Service | Runs On | Responsibility |
|---------|---------|---------------|
| **Frontend + API** | Vercel | Next.js 14 (App Router + API Routes). Auth (NextAuth), Stripe webhooks, REST endpoints, SSE streaming. Inngest functions for pipeline orchestration. |
| **Browser Workers** | Railway (dedicated containers) | FastAPI internal API. Playwright browser instances. One browser process per user. ARQ consumer for browser tasks. Optional noVNC on demand. |

**Key simplification**: By using Inngest on Vercel, we eliminate the separate API Gateway and Orchestrator services. Inngest functions run as Vercel serverless functions — they handle the LangGraph pipeline orchestration with step-level retry. Only browser-bound work runs on Railway.

### Job Queue — Inngest (Vercel-native) + ARQ (Browser Workers)

**Hybrid approach**: Inngest for orchestration logic (runs on Vercel), ARQ for browser-bound work (runs on Railway).

**Why Inngest?** It runs your code on Vercel — no separate runtime to manage. It splits long-running workflows into individually retried steps, persists output across steps, and handles failures/retries automatically. Perfect for the LangGraph pipeline orchestration.

**Why keep ARQ for browsers?** Playwright needs persistent containers with Chromium, which can't run on Vercel's serverless functions. Browser workers stay on Railway with ARQ for browser-specific tasks.

```
User clicks "Start Session"
  ↓
Next.js API route → Stripe check → triggers Inngest function
  ↓
Inngest orchestrates pipeline steps (each step is individually retryable):
  step.run("intake")       → Claude API call (runs on Vercel)
  step.run("discovery")    → enqueues browser task to ARQ → waits for result
  step.run("scoring")      → Claude API call (runs on Vercel)
  step.run("resume-tailor")→ Claude API call (runs on Vercel)
  step.waitForEvent("user-approval")  → HITL pause (built-in!)
  step.run("apply-batch")  → enqueues browser tasks to ARQ → streams progress
  step.run("verify")       → Claude API call
  step.run("report")       → Claude API call + email via Resend
  ↓
Each step publishes events to Redis pub/sub → SSE/WebSocket to frontend
```

**Inngest advantages over pure ARQ:**
- Built-in step-level retry with exponential backoff
- `step.waitForEvent()` is perfect for HITL — no need for LangGraph `interrupt()`
- Built-in event replay / debugging dashboard
- Concurrency controls (limit 5 concurrent applications per user)
- Automatic function versioning

**Task granularity** (3 levels):
1. **Session function** (Inngest): Orchestrates the full pipeline as a series of steps
2. **Application task** (ARQ on Railway): One per job — browser context lifecycle
3. **Form-fill actions**: Individual Playwright actions within an application (for retry)

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

### Backend
- **Python 3.12** + **FastAPI** (API Gateway, async throughout)
- **LangGraph** for agent orchestration + state machine
- **Inngest** for pipeline orchestration (step-level retry, HITL via `waitForEvent`, runs on Vercel)
- **ARQ** for browser-specific tasks (Redis-backed, runs on Railway workers)
- **Playwright** (async) for browser automation (discovery scraping)
- **Patchright** for anti-detection (patched Playwright fork)
- **browser-use** for AI-driven job application (LLM-controlled browser agent, replaces hardcoded selectors)
- **Claude API** (Anthropic SDK) — Opus, Sonnet, Haiku
- **PostgreSQL** + **AsyncPostgresSaver** for checkpointing + data persistence
- **Neo4j Aura** for application strategy knowledge graph
- **Redis** for job queue (ARQ), pub/sub (status events, chat), rate limiting

### Frontend
- **Next.js 14** (App Router, TypeScript) — from scratch with shadcn/ui
- **Tailwind CSS** + **shadcn/ui** component library
- **Stripe.js** + **Stripe Checkout** (hosted payment page, minimal PCI scope)
- **NextAuth.js** for authentication (email + Google OAuth)

### Infrastructure
- **Vercel** — Frontend hosting (edge functions, preview deploys, custom domain)
- **Railway** — API Gateway + Orchestrator + Browser Workers (persistent containers, WebSocket support, autoscaling)
- **Neon** — Managed Postgres (serverless, connection pooling, branching for dev/staging)
- **Upstash** — Managed Redis (ARQ queue, pub/sub, rate limiting)
- **Neo4j Aura** — Knowledge graph (free tier: 200K nodes, 400K relationships)
- **Cloudflare** — CDN, DDoS protection, US-only WAF geo-restriction
- **Stripe** — Checkout, Subscriptions, Customer Portal, Webhooks
- **Resend** — Transactional emails (receipts, session summaries, weekly reports)
- **Sentry** — Error tracking + performance monitoring
- **BrightData** or **Oxylabs** — Residential proxy rotation for job board access (~$50-200/mo)

---

## Database Design

### Postgres (Neon) — Relational + Transactional
```sql
users (
  id UUID PK, email, name, stripe_customer_id, stripe_subscription_id,
  plan TEXT, geo_country, created_at, updated_at
)

sessions (
  id UUID PK, user_id FK, status, keywords JSONB, locations JSONB,
  preferences JSONB, applications_target INT, applications_completed INT,
  started_at, ended_at, resumed_from UUID nullable
)

jobs_discovered (
  id UUID PK, session_id FK, title, company, url, board,
  ats_type, score INT, status, discovered_at
)

applications (
  id UUID PK, session_id FK, job_id FK, status,
  cover_letter_text, screenshot_url, error_message,
  submitted_at, duration_seconds INT
)

resumes (
  id UUID PK, user_id FK, original_text_encrypted BYTEA,
  file_url_encrypted BYTEA, uploaded_at
  -- encrypted with pgcrypto AES-256, auto-deleted after 30 days
)

stripe_events (
  id UUID PK, stripe_event_id UNIQUE, type, data JSONB,
  processed BOOL, idempotency_key, created_at
)
```

### Neo4j Aura — Knowledge Graph (Cross-Session Learning)
```
Nodes:
  (:Company {name, domain, size, industry})
  (:JobBoard {name})               — Indeed, LinkedIn, Glassdoor, etc.
  (:ATSPlatform {name, version})   — Workday, Greenhouse, Lever, iCIMS, Taleo
  (:FormField {label, type, common_values})
  (:ApplicationStrategy {name, steps_json, success_rate})
  (:Question {text, category})     — Screening questions encountered
  (:Answer {text, effectiveness})  — Answers that led to callbacks

Relationships:
  (:Company)-[:USES_ATS]->(:ATSPlatform)
  (:Company)-[:POSTS_ON]->(:JobBoard)
  (:ATSPlatform)-[:HAS_FORM_FIELD]->(:FormField)
  (:ATSPlatform)-[:REQUIRES_STRATEGY]->(:ApplicationStrategy)
  (:Question)-[:ASKED_BY]->(:Company)
  (:Question)-[:BEST_ANSWERED_WITH]->(:Answer)

Value:
  - Application Agent queries Neo4j before opening a form: "What ATS does Company X use?
    What fields will I see? What strategy has the highest success rate?"
  - Cross-session learning: successful patterns feed back into the graph
  - Scoring Agent uses ATS data to estimate application difficulty
```

---

## Pricing (Weekly Subscription)

Weekly billing is better than hourly because:
- Job searches are urgent — people want to solve it *this week*
- Reduces perceived commitment vs monthly ($49/week feels lower than $200/month)
- Avoids the anxiety of watching a clock while the bot works
- Aligns incentives: fast sessions are good for us (less infra), and the user isn't punished for speed

| Tier | Price | Applications/Week | Features | Best For |
|------|-------|-------------------|----------|----------|
| **Starter** | $49/week | 25 | SSE Status Feed | Dipping toes, light search |
| **Professional** | $99/week | 75 | SSE + Chat Steering | Active job seekers |
| **Executive** | $199/week | 200 | SSE + Chat + Priority Support | Serious search, full control |

### Payment Flow (Stripe)
```
1. User signs up → Stripe Customer created
2. User selects plan → Stripe Checkout (weekly subscription)
3. Session starts → Backend checks plan limits (apps remaining this week)
4. Session runs → applications_used counter increments per submission
5. Weekly reset → counter resets, subscription renews
6. Cancel anytime → Stripe Customer Portal
```

### Margin Analysis (at 100 subscribers/week)

| | Starter (40%) | Professional (40%) | Executive (20%) |
|--|---------------|---------------------|-----------------|
| Revenue/week | 40 × $49 = $1,960 | 40 × $99 = $3,960 | 20 × $199 = $3,980 |
| Claude API | 40 × $8 = $320 | 40 × $20 = $800 | 20 × $44 = $880 |
| Infra share | $100 | $200 | $300 |
| **Weekly total** | **Revenue: $9,900 — Costs: $2,600 — Margin: 74%** |
| **Monthly** | **Revenue: ~$40K — Gross profit: ~$29K** |

---

## US-Only Access

### Geo-Restriction (Defense in Depth)
1. **Cloudflare WAF** — Firewall rule blocking all non-US traffic at CDN edge (free tier)
2. **NextAuth middleware** — Server-side IP check via MaxMind GeoLite2 DB on signup + session start
3. **Stripe** — Payment method restricted to US-issued cards
4. **Landing page** for non-US visitors: "Currently available in the United States only. Join the waitlist."

---

## Security & Data Privacy

### Resume / PII
- Encrypt resumes at rest with `pgcrypto` AES-256 in Postgres
- Auto-delete resumes 30 days after last session unless user opts to retain
- Field-level encryption for name, email, phone, address
- "Delete my data" endpoint from day one (CCPA/GDPR compliance)

### Job Board Credentials
- **Never store passwords.** Use "bring your own session" model:
  - User logs into job boards during a Takeover phase
  - Agent uses those authenticated browser sessions (cookies only)
  - Encrypted cookie jar stored per user, separate from main DB
- For boards with OAuth (LinkedIn): use OAuth tokens with scoped permissions

### Payment Security
- Stripe Checkout (hosted page) — zero PCI scope on our side
- Never store card details
- Idempotency keys on all Stripe webhook handlers

### Infrastructure
- Railway private networking between services
- Neon Postgres with enforced SSL + connection pooling
- Short-lived JWTs (15-min expiry) + refresh tokens
- Separate browser process per user (not shared BrowserContext) for session isolation
- Ephemeral `/tmp/{session_id}/` storage per session, cleaned up on completion

---

## Resilience & Error Handling

### Circuit Breaker
- Track `consecutive_failures` in state
- After 3 consecutive application failures to the same ATS type → pause and alert user
- "The agent is having trouble with Workday applications. Would you like to skip remaining Workday jobs or take control?"

### Per-Application Retry
- Each application is an independent ARQ subtask
- If a browser context crashes → spin up new context, retry from scratch
- If an LLM call fails → exponential backoff, 3 retries
- Progress saved to Postgres after each successful application → sessions resume from last checkpoint

### Graceful Degradation
- If LinkedIn blocks the bot → skip LinkedIn, continue with other boards, notify user
- If Neo4j is down → fall back to stateless form filling (no strategy lookup)
- If Redis pub/sub drops → SSE reconnects automatically, client polls for missed events

---

## Marketplace & Distribution

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
│   ├── gateway/                    # API Gateway service
│   │   ├── main.py                # FastAPI app
│   │   ├── routes/
│   │   │   ├── auth.py            # JWT auth + signup/login
│   │   │   ├── sessions.py        # Session CRUD + SSE streaming
│   │   │   ├── payments.py        # Stripe webhooks + checkout
│   │   │   └── health.py
│   │   ├── middleware/
│   │   │   ├── geo.py             # US-only geofencing
│   │   │   └── rate_limit.py
│   │   └── config.py
│   ├── orchestrator/               # LangGraph pipeline service
│   │   ├── worker.py              # ARQ worker entry point
│   │   ├── pipeline/
│   │   │   ├── graph.py           # LangGraph StateGraph definition
│   │   │   ├── state.py           # JobHunterState TypedDict
│   │   │   └── nodes.py           # Node wrappers + routing
│   │   └── agents/
│   │       ├── intake.py
│   │       ├── career_coach.py    # Resume rewrite, impostor coaching, LinkedIn advice
│   │       ├── discovery.py
│   │       ├── scoring.py
│   │       ├── resume_tailor.py
│   │       ├── application.py
│   │       ├── verification.py
│   │       └── reporting.py
│   ├── browser/                    # Browser worker service
│   │   ├── manager.py             # Browser lifecycle management
│   │   ├── tools/
│   │   │   ├── job_boards/
│   │   │   │   ├── indeed.py
│   │   │   │   ├── linkedin.py
│   │   │   │   ├── glassdoor.py
│   │   │   │   ├── ziprecruiter.py
│   │   │   │   └── google_jobs.py
│   │   │   ├── browser_use_applier.py  # AI-driven application via browser-use (primary)
│   │   │   ├── form_filler.py     # Dynamic form analysis + filling (fallback)
│   │   │   ├── account_creator.py # Workday/Greenhouse account creation (fallback)
│   │   │   └── cover_letter.py    # Cover letter generation
│   │   └── anti_detect/
│   │       └── stealth.py         # Patchright config, random delays
│   ├── shared/
│   │   ├── models/
│   │   │   ├── schemas.py         # Pydantic models
│   │   │   └── db.py              # SQLAlchemy models
│   │   ├── neo4j_client.py        # Knowledge graph queries
│   │   ├── redis_client.py        # Redis connections
│   │   └── security.py            # Encryption helpers
│   ├── docker-compose.yml         # Local dev: Postgres, Redis, Neo4j
│   ├── Dockerfile.gateway
│   ├── Dockerfile.orchestrator
│   ├── Dockerfile.browser
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx               # Landing page + pricing
│   │   ├── dashboard/page.tsx     # User dashboard (sessions, history)
│   │   ├── session/
│   │   │   ├── new/page.tsx       # Keyword input + resume upload + plan check
│   │   │   └── [id]/page.tsx      # Live session: tiered viewing + chat + status
│   │   ├── auth/
│   │   │   ├── login/page.tsx
│   │   │   └── signup/page.tsx
│   │   └── layout.tsx
│   ├── components/
│   │   ├── StatusFeed.tsx         # SSE text updates
│   │   ├── ChatPanel.tsx          # Steering chat interface
│   │   ├── SessionProgress.tsx    # Pipeline step indicator
│   │   ├── JobCard.tsx            # Job listing with score
│   │   ├── ResumeScoreCard.tsx    # Resume fit score display
│   │   ├── CoachPanel.tsx        # Career Coach output: rewritten resume, advice, confidence boost
│   │   ├── LinkedInAdvice.tsx    # LinkedIn profile improvement checklist
│   │   ├── ApplicationLog.tsx     # Real-time application feed
│   │   ├── PricingTable.tsx       # Starter / Pro / Executive
│   │   └── GeoGate.tsx            # US-only message for blocked users
│   ├── lib/
│   │   ├── api.ts                 # REST + SSE client
│   │   └── stripe.ts              # Stripe client helpers
│   └── package.json
└── README.md
```

---

## Implementation Order

### Phase 1: Foundation (Week 1-2)
1. Repo scaffolding (monorepo, 3 backend services, frontend)
2. Docker Compose: Postgres, Redis, Neo4j local
3. LangGraph state schema + graph definition
4. ARQ worker setup with Redis
5. Intake agent (keyword parsing + resume upload)
6. Discovery agent (Indeed + Google Jobs via Playwright)
7. Scoring agent (job-to-profile matching)
8. Basic SSE status feed (reuse mayo-clinic pattern)

### Phase 2: Application Engine (Week 2-3)
9. Application agent with Playwright form filling
10. Cover letter generator (Claude Opus)
11. Resume tailor agent + fit scoring
12. Account creation logic (Workday, Greenhouse detection)
13. Verification agent (screenshot + confirmation check)
14. Circuit breaker + per-application retry logic
15. Neo4j seeding with initial ATS strategies

### Phase 3: Live Steering (Week 3-4)
16. Screenshot feed: CDP capture → Redis pub/sub → WebSocket → canvas
17. Chat panel + message injection into LangGraph state
18. noVNC on-demand setup (Xvfb + x11vnc + websockify)
19. Mode toggle UI (Status → Screenshot+Chat → Takeover)
20. HITL interrupt points (shortlist review, obstacle pause)

### Phase 4: Payments + Auth + Security (Week 4-5)
21. NextAuth.js (email + Google OAuth)
22. Stripe integration (subscriptions, weekly plans, Customer Portal)
23. US-only geofencing (Cloudflare WAF + MaxMind)
24. Resume encryption (pgcrypto AES-256)
25. "Delete my data" endpoint
26. Reporting agent + session summary emails (Resend)

### Phase 5: Deploy + Launch (Week 5-6)
27. Vercel deploy (frontend) + Railway deploy (3 backend services)
28. Neon Postgres + Upstash Redis + Neo4j Aura provisioning
29. Anti-detection (Patchright, residential proxies, random delays)
30. Landing page + pricing page
31. Sentry error tracking
32. Upwork / Fiverr listings
33. Product Hunt launch

---

## Scaling Roadmap

| Users | Infra | Monthly Cost | Changes Needed |
|-------|-------|-------------|----------------|
| 1-10 | 1 gateway, 1 orchestrator, 2 browser workers | ~$150 | None |
| 10-50 | 1 gateway, 2 orchestrators, 5 browser workers | ~$400 | Railway autoscaling |
| 50-100 | 2 gateways (load balanced), 3 orchestrators, 10 browser workers | ~$900 | Session-affine routing |
| 100-500 | Railway autoscaling across all services | ~$3,000 | Kubernetes evaluation |
| 500+ | Migrate to Kubernetes (EKS/GKE) | ~$8,000+ | Full K8s migration |

---

## Verification / Testing

- **Unit tests**: Each agent in isolation with mocked LLM responses (pytest)
- **Integration tests**: Full pipeline with test job listings
- **E2E tests**: Playwright tests against staging Workday/Greenhouse instances
- **Load test**: Concurrent WebSocket connections + ARQ queue throughput
- **Manual QA**: Run a live session, apply to real jobs, verify submissions
- **Billing test**: Stripe test mode — verify subscription creation, plan limits, cancellation
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
- **Models**: Claude Opus/Sonnet/Haiku with smart routing (Opus only where reasoning quality matters)
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

## Secrets & API Key Safety

**Zero secrets in source control. Ever.**

### .gitignore (committed to repo)
```
# Environment
.env
.env.*
!.env.example

# Keys
*.pem
*.key
credentials.json

# IDE
.vscode/
.idea/

# Python
__pycache__/
*.pyc
venv/
.venv/

# Node
node_modules/
.next/

# OS
.DS_Store
```

### .env.example (committed — shows structure, no values)
```bash
# Claude API
ANTHROPIC_API_KEY=sk-ant-xxx

# Stripe
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_xxx

# Database
DATABASE_URL=postgresql://user:pass@host:5432/db
NEO4J_URI=neo4j+s://xxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=xxx

# Redis
REDIS_URL=redis://default:xxx@xxx.upstash.io:6379

# Auth
NEXTAUTH_SECRET=xxx
NEXTAUTH_URL=http://localhost:3000
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx

# Inngest
INNGEST_EVENT_KEY=xxx
INNGEST_SIGNING_KEY=xxx

# Email
RESEND_API_KEY=re_xxx

# Geo
MAXMIND_LICENSE_KEY=xxx

# Sentry
SENTRY_DSN=https://xxx@sentry.io/xxx

# Proxy (for anti-detection)
PROXY_URL=http://user:pass@proxy.brightdata.com:22225
```

### Runtime Secret Management
- **Vercel**: Secrets stored in Vercel Environment Variables (encrypted at rest, per-environment)
- **Railway**: Secrets stored in Railway Variables (encrypted, per-service)
- **Pre-commit hook**: `detect-secrets` or `trufflehog` to scan for accidentally committed keys
- **CI/CD**: GitHub Actions secrets for deployment pipelines
- **Never log secrets**: Custom log formatter strips any string matching `sk-`, `whsec_`, `re_`, etc.

---

## Legal

- **V2 Software LLC** — already established, limits personal liability
- **Terms of Service**: Users acknowledge automated applications may violate job board ToS; users accept responsibility
- **Privacy Policy**: CCPA/GDPR compliant. Data retention policy. Right to deletion.
- **No guarantees** of interview/hire outcomes
- **Liability insurance** (E&O / Professional Liability) recommended
- **Disclaimer**: "This service assists with job applications. Results vary. Not affiliated with any job board or ATS platform."
