# JobHunter Agent — AI-Powered Autonomous Job Application Platform

An open-source AI agent that discovers jobs, scores them against your resume, tailors applications, and submits them autonomously — with a live browser feed so you can watch and intervene in real time.

**Built with:** FastAPI + LangGraph (Python) | Next.js 14 | Skyvern (AI form filler) | Bright Data MCP (job discovery) | EvoAgentX (self-improving prompts)

**Live at:** [jobhunteragent.com](https://jobhunteragent.com)

---

## How It Works

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
│  Next.js 14 │     │ FastAPI (port 8000)                  │
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
- Python 3.11+
- Node.js 18+
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
| Frontend | Next.js 14 + Tailwind + shadcn/ui |
| Form Filling | Skyvern (self-hosted, Claude vision) |
| Job Discovery | Bright Data MCP + Greenhouse API |
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
│   └── src/app/              # Next.js 14 App Router
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
