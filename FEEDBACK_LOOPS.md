# Self-Improving Agent Feedback Loops

Two independent feedback loops that make the JobHunter agent get smarter over time — one from community signals, one from its own outcomes.

---

## Loop 1: Moltbook — Community Feedback Loop

Social learning from an agent community network. The agent posts its results, the community reacts, and the agent calibrates.

```
                        MOLTBOOK COMMUNITY FEEDBACK LOOP
                        ================================

    +------------------+
    |   JobHunter      |
    |   Agent runs     |
    |   sessions       |
    +--------+---------+
             |
             | anonymized metrics
             | (success rate, top board, blockers)
             v
    +------------------+        post results         +------------------+
    |   Feedback Loop  | --------------------------> |   Moltbook.com   |
    |   (cron: 30min)  |                             |   Agent Feed     |
    |                  | <-------------------------- |                  |
    |   - post metrics |     votes + comments        |   Other agents   |
    |   - scan feed    |     (community signals)     |   vote & comment |
    |   - comment      |                             +------------------+
    +--------+---------+
             |
             | engagement data (upvotes, downvotes, comments)
             v
    +------------------+
    |  Signal          |     >= 5 consistent signals
    |  Accumulator     | --------------------------+
    |                  |                           |
    |  - vote ratios   |                           v
    |  - comment       |              +------------------------+
    |    sentiment     |              |   Prompt Patch         |
    |  - topic extract |              |   Generation           |
    +------------------+              |                        |
                                      |  "Calibration: scores  |
                                      |   are miscalibrated,   |
                                      |   be more conservative"|
                                      +----------+-------------+
                                                 |
                                                 | injected into
                                                 v
                                      +------------------------+
                                      |  ## Community-Calibrated|
                                      |  ## Adjustments         |
                                      |                        |
                                      |  Appended to scoring   |
                                      |  & discovery system    |
                                      |  prompts               |
                                      +------------------------+

                        DREAM CYCLE (every 5th cron run / ~2.5 hrs)
                        ============================================

    +------------------+       last 20 audits        +------------------+
    |  Recent Audit    | --------------------------> |  Claude Sonnet   |
    |  Records +       |       + engagement data     |  (reflection)    |
    |  Engagement      |       + existing patches    |                  |
    +------------------+                             |  "What patterns  |
                                                     |   do you see?"   |
                                                     +--------+---------+
                                                              |
                                                              | 3-5 compressed
                                                              | insights
                                                              v
                                                     +------------------+
                                                     |  Dream Log       |
                                                     |  (max 10)        |
                                                     |                  |
                                                     |  - prunes bad    |
                                                     |    patches       |
                                                     |  - consolidates  |
                                                     |    learnings     |
                                                     |  - injected into |
                                                     |    future prompts|
                                                     +------------------+
```

### Key talking points:

- **Social signal threshold**: Requires 5+ consistent community signals before any prompt patch is accepted — prevents single-post manipulation
- **Human review flag**: After 10+ auto-adjustments, patches are suppressed until human reviews — safety guardrail against drift
- **Dream cycle = memory consolidation**: Inspired by how biological sleep consolidates learning. Every ~2.5 hours, an LLM reflects on recent performance and compresses insights into durable learnings
- **Contradiction pruning**: Dreams can remove prompt patches that contradict new insights (e.g., dream says "be more lenient" removes a patch saying "be more conservative")
- **Security**: All external content is sanitized before LLM use — prevents prompt injection from community posts

---

## Loop 2: EvoAgentX — Automated Prompt Optimization

Self-optimizing prompts using gradient-based evolution. The agent tracks its own outcomes and evolves the prompts that drive it.

```
                    EVOAGENTX PROMPT OPTIMIZATION LOOP
                    ===================================

    +------------------+
    |   User starts    |
    |   job search     |
    |   session        |
    +--------+---------+
             |
             | session runs through pipeline
             v
    +------------------+     live prompts      +------------------+
    |  Discovery       | <------------------- |  Prompt Registry  |
    |  Agent           |                      |  (Postgres)       |
    +--------+---------+                      |                   |
             |                                |  - versioned      |
             v                                |  - rollback-able  |
    +------------------+     live prompts     |  - audit trail    |
    |  Scoring         | <------------------- |                   |
    |  Agent           |                      +--------+----------+
    +--------+---------+                               ^
             |                                         |
             v                                         | evolved prompts
    +------------------+                               | (new version)
    |  Application     |                               |
    |  Agent (Skyvern) |                      +--------+----------+
    +--------+---------+                      |  EvoAgentX        |
             |                                |  TextGrad Runner  |
             | outcome recorded               |                   |
             v                                |  Sonnet = judge   |
    +------------------+                      |  (scores prompts) |
    |  Reporting       |                      |                   |
    |  Agent           |                      |  Haiku = executor  |
    |                  |                      |  (runs candidates) |
    +--------+---------+                      +--------+----------+
             |                                         ^
             | success/failure + metadata              |
             v                                         |
    +------------------+    every 10 sessions  +-------+----------+
    |  Outcome Store   | -------------------> |  Optimization     |
    |  (Postgres)      |    trigger evolve    |  Trigger          |
    |                  |                      |                   |
    |  - board used    |                      |  "10 sessions     |
    |  - ATS type      |                      |   completed,      |
    |  - success/fail  |                      |   time to evolve" |
    |  - blocker type  |                      +-------------------+
    |  - score given   |
    +------------------+


                    TEXTGRAD EVOLUTION DETAIL
                    =========================

    +------------------+
    |  Current Prompt   |     "Score these jobs based on
    |  (v3)            |      relevance, skills match..."
    +--------+---------+
             |
             | Sonnet analyzes outcomes:
             | "v3 scored 62% — jobs rated 8+
             |  had 40% application success.
             |  Scoring overweights title match."
             v
    +------------------+
    |  Gradient Signal  |     "Reduce title-match weight,
    |  (text-based)    |      increase skills-overlap and
    |                  |      company-stage signals"
    +--------+---------+
             |
             | apply gradient to prompt text
             v
    +------------------+
    |  Candidate        |     "Score these jobs based on
    |  Prompt (v4)     |      skills overlap, company stage,
    |                  |      and role requirements..."
    +--------+---------+
             |
             | Haiku runs candidate on held-out data
             | Sonnet scores result quality
             v
    +------------------+
    |  Accept / Reject  |     score(v4) > score(v3)?
    |                  |
    |  YES: save v4    |     Prompt Registry: v3 -> v4
    |  NO:  keep v3    |     (v3 preserved for rollback)
    +------------------+
```

### Key talking points:

- **TextGrad**: Text-based gradient descent for prompts. Instead of numerical gradients, Sonnet generates natural language "gradients" describing what to change and why
- **Dual-model architecture**: Haiku (cheap/fast) executes prompt candidates on test data, Sonnet (smart/expensive) judges quality and generates optimization signals — cost-efficient evolution
- **Versioned prompt registry**: Every prompt version is stored in Postgres with timestamps and parent references. Can rollback to any previous version if a new one degrades performance
- **Outcome-driven**: Evolution is triggered by real session outcomes (did the user actually get applications submitted?), not synthetic benchmarks
- **Every 10 sessions**: Batch size of 10 balances signal quality (enough data points) with responsiveness (don't wait too long to improve)
- **Safety**: New prompts must score higher than current ones on held-out data before being promoted. Bad mutations are discarded, not deployed

---

## How They Work Together

```
                         TWO LOOPS, ONE AGENT
                         =====================

              EXTERNAL SIGNAL                    INTERNAL SIGNAL
              (community)                        (own outcomes)

         +------------------+              +------------------+
         |    Moltbook      |              |    EvoAgentX     |
         |    Community     |              |    Optimizer     |
         +--------+---------+              +--------+---------+
                  |                                 |
                  | prompt patches                  | evolved prompts
                  | + dream insights                | (versioned)
                  |                                 |
                  v                                 v
         +------------------------------------------------+
         |                                                |
         |            SYSTEM PROMPTS                      |
         |            (Discovery + Scoring)                |
         |                                                |
         |   Base prompt                                  |
         |   + Community-Calibrated Adjustments (Moltbook)|
         |   + Consolidated Insights (Dreams)             |
         |   + Evolved prompt text (EvoAgentX)            |
         |                                                |
         +------------------------+------------------------+
                                  |
                                  v
                    +---------------------------+
                    |   Better job discovery,   |
                    |   better scoring,         |
                    |   better applications     |
                    +---------------------------+
```

---

## Loop 3: Application Feedback — ATS-Specific Strategy Learning

Learns from every Skyvern application attempt. Tracks success/failure patterns per ATS type and generates strategies that get injected into future applications.

```
                    APPLICATION FEEDBACK LOOP
                    =========================

    +------------------+
    |   Skyvern fills  |
    |   application    |
    |   form           |
    +--------+---------+
             |
             | result: submitted / failed / skipped
             | + error_category, failure_step, ats_type
             v
    +------------------+
    |  application_    |     Postgres table — every attempt recorded
    |  results         |     immediately with full metadata
    |  (Postgres)      |
    +--------+---------+
             |
             | queried at end of each session
             | (grouped by ats_type)
             v
    +------------------+     >= 5 attempts per ATS
    |  Application     | --------------------------+
    |  Feedback        |                           |
    |  Analyzer        |                           v
    |                  |              +------------------------+
    |  - success rate  |              |   Haiku LLM            |
    |  - top errors    |              |   Strategy Generator   |
    |  - failure steps |              |                        |
    +------------------+              |  Input: "Greenhouse:   |
                                      |   72% success, top     |
                                      |   error: form_fill,    |
                                      |   top step: submit"    |
                                      |                        |
                                      |  Output: "Greenhouse   |
                                      |   forms are multi-page.|
                                      |   Click Next/Continue  |
                                      |   between sections.    |
                                      |   File uploads need    |
                                      |   Browse click."       |
                                      +----------+-------------+
                                                 |
                                                 | upsert
                                                 v
                                      +------------------------+
                                      |  ats_strategies        |
                                      |  (Postgres)            |
                                      |                        |
                                      |  greenhouse: "..."     |
                                      |  lever: "..."          |
                                      |  workday: "..."        |
                                      +----------+-------------+
                                                 |
                                      +----------+----------+
                                      |                     |
                                      v                     v
                             Skyvern nav goal      Resume tailoring
                             (ATS tips appended)   (ATS formatting
                                                    guidance added
                                                    to system prompt)


                    DATA FLOW EXAMPLE
                    =================

    Session 1: Greenhouse app → FAILED (form_fill_error, step: submit)
    Session 2: Greenhouse app → SUBMITTED
    Session 3: Greenhouse app → FAILED (timeout)
    Session 4: Greenhouse app → SUBMITTED
    Session 5: Greenhouse app → FAILED (form_fill_error, step: form_fill)
                                                    |
                                                    | 5 attempts reached
                                                    v
    Haiku analyzes: "60% success, 40% form_fill_error, submit/form_fill steps"
                                                    |
                                                    v
    Strategy: "Greenhouse forms are multi-page with Next/Continue
              between sections. Scroll down to find all required
              fields before clicking Submit. File upload fields
              require clicking Browse, not drag-and-drop."
                                                    |
                                                    v
    Session 6+: Skyvern receives ATS tips in navigation goal
                Resume tailored with ATS-aware formatting
```

### Key talking points:

- **Pure outcome-driven**: No community signals or LLM reflection needed — learns directly from what worked and what didn't
- **Per-ATS specialization**: Different ATS platforms have radically different form patterns (Greenhouse = multi-page, Workday = single-page with tabs, Lever = simple). One-size-fits-all prompts miss these differences
- **5-attempt threshold**: Same signal threshold as the other loops — don't over-react to 1-2 data points
- **Dual injection**: Tips go into both the Skyvern navigation goal (how to fill the form) AND resume tailoring (how to format for that ATS's parser)
- **Cost**: ~$0.001 per strategy generation (Haiku). Only regenerates when new outcomes arrive. Negligible.
- **Fallback**: If LLM call fails, uses rule-based fallback mapping common error categories to tips

---

## How All Three Loops Work Together

```
                      THREE LOOPS, ONE AGENT
                      =======================

         EXTERNAL SIGNAL           INTERNAL SIGNAL          TACTICAL SIGNAL
         (community)               (prompt evolution)       (ATS outcomes)

    +------------------+     +------------------+     +------------------+
    |    Moltbook      |     |    EvoAgentX     |     |    Application   |
    |    Community     |     |    Optimizer     |     |    Feedback      |
    +--------+---------+     +--------+---------+     +--------+---------+
             |                        |                        |
             | prompt patches         | evolved prompts        | ATS strategy
             | + dream insights       | (versioned)            | tips
             |                        |                        |
             v                        v                        v
    +----------------------------------------------------------------+
    |                                                                |
    |                    AGENT PROMPTS & BEHAVIOR                    |
    |                                                                |
    |   Discovery prompts  (Moltbook + EvoAgentX)                   |
    |   Scoring prompts    (Moltbook + EvoAgentX)                   |
    |   Skyvern nav goal   (Application Feedback)                   |
    |   Resume tailoring   (Application Feedback)                   |
    |   Board priorities   (Moltbook)                               |
    |                                                                |
    +------------------------------+---------------------------------+
                                   |
                                   v
                     +---------------------------+
                     |   Better job discovery,   |
                     |   better scoring,         |
                     |   better form filling,    |
                     |   better resume matching  |
                     +---------------------------+
```

### The key insight for interviews:

> "We built three orthogonal learning loops, each operating at a different level of abstraction. **Moltbook** gives us *social intelligence* — what the broader agent community thinks about scoring calibration and strategy. **EvoAgentX** gives us *empirical intelligence* — evolving the prompts that drive discovery and scoring using gradient-based optimization on session outcomes. **Application Feedback** gives us *tactical intelligence* — learning ATS-specific form-filling patterns from our own success/failure data. They're independent, safety-gated, and target different parts of the pipeline: Moltbook and EvoAgentX optimize *what jobs to find and how to score them*, while Application Feedback optimizes *how to actually submit the application*."

### Technical depth for follow-up questions:

- **"How do you prevent prompt drift?"** — 5-signal threshold for Moltbook patches, human review flag at 10+ adjustments, versioned registry with rollback for EvoAgentX, dream cycle prunes contradictory patches, ATS strategies require 5+ attempts before activating
- **"How do you handle adversarial community input?"** — All content sanitized (strips prompt injection, HTML, base64), patches require consistent signal direction across multiple posts, dreams consolidate and prune
- **"What's the cost?"** — Haiku for execution (~$0.001/eval), Sonnet for judgment (~$0.01/optimization), dream cycles every ~2.5 hours, ATS strategy generation ~$0.001/call. Total optimization cost is a few dollars/day
- **"How is this different from fine-tuning?"** — No model weights changed. We're optimizing the *prompts*, not the model. Faster iteration (minutes vs hours), fully reversible, works with any model version, no training data requirements
- **"Why three separate loops instead of one?"** — Each targets a different part of the pipeline with a different signal source. Moltbook = external community wisdom. EvoAgentX = statistical prompt optimization. Application Feedback = tactical ATS knowledge. Keeping them independent means a failure in one doesn't break the others, and each can evolve at its own pace
