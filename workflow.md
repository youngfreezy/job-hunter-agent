# Workflow Orchestration & Core Principles

## Workflow Orchestration

### 1. Plan Node Default
- Enter plan mode for any non-trivial task (3+ steps or architectural decisions)
- If execution goes sideways, stop and re-plan immediately
- Use planning for verification steps, not just implementation
- Write detailed specs up front

### 2. Subagent Strategy
- Use subagents aggressively for research/exploration and parallel analysis
- Keep one focused task per subagent

### 3. Self-Improvement Loop
- After any user correction, update `tasks/lessons.md`
- Add prevention rules, not just observations
- Review relevant lessons at session start

### 4. Verification Before Done
- Do not mark complete without proof
- Run tests, inspect logs, and validate behavior
- Compare previous and new behavior where relevant

### 5. Demand Elegance (Balanced)
- For non-trivial changes, evaluate cleaner alternatives
- Avoid over-engineering simple fixes

### 6. Autonomous Bug Fixing
- Fix reported bugs directly with minimal user back-and-forth
- Drive from logs/errors/failing tests

## Task Management
1. Plan first in `tasks/todo.md` with checkboxes
2. Track progress by marking items complete
3. Add a review section with outcomes and verification
4. Capture corrections and new safeguards in `tasks/lessons.md`

## Core Principles
- Simplicity first
- No lazy fixes; solve root causes
- Minimal impact changes
