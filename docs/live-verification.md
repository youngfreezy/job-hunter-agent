# Live Verification Status

Last updated: March 7, 2026

This document is the source of truth for what has been verified end-to-end with live API calls and real browser interactions. It separates proven runtime behavior from roadmap/design material elsewhere in the repo.

## Environment

- Start command: `./scripts/start-app.sh`
- Finder/macOS launcher: `JobHunter Agent.app`
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Verification mode: no mocks, live backend, live browser automation, real SSE/WebSocket traffic

## Live-Verified Features

- Session wizard creates real sessions from the UI
- Session page rehydrates from backend state and replays streamed events after refresh
- Career coach review gate pauses the workflow and resumes after approval
- Shortlist review gate surfaces reviewed jobs and resumes the workflow after approval
- Job discovery, scoring, resume tailoring, apply, verify, and reporting run through the real backend pipeline
- Manual intervention works for blocked applications: the workflow emits intervention-needed state and can resume after operator action
- Session steering chat is backed by an LLM judge over live session state and recent events
- Workflow supervision now runs as a graph-owned control step between major stages, with saved-review resume support for pausing at human-review interrupts
- Screenshot streaming works in the session UI
- Browser takeover works end-to-end through the UI screenshot/input relay
- Manual apply log shows real submitted jobs with persisted cover letter and tailored resume

## Runtime Path That Is Proven

- The verified takeover path on macOS is the in-app screenshot stream plus WebSocket input relay
- Control is requested from the UI, frames render in the session page, and mouse/keyboard events reach the real Playwright page
- The verified steering path uses `/api/sessions/{id}/steer` for operator input and a graph-owned supervisor step for workflow control between stages

## Not Proven Or Not Yet Implemented

- The older noVNC/X11 takeover scaffold exists in the codebase but was not the live runtime path used in verification
- Interactive coach chat that rewrites the coached resume live in response to chat messages is not implemented
- Open-source packaging is incomplete; the repo is still coupled to local backend/runtime assumptions and needs packaging/docs separation for standalone OSS readiness
- The macOS `.app` wrapper currently launches through Terminal for reliable Desktop file access; a fully silent signed app wrapper is still future work

## Live Tests Run

The following Playwright specs were used for live verification:

- `frontend/tests/e2e/full-flow.spec.ts`
- `frontend/tests/e2e/pipeline-e2e.spec.ts`
- `frontend/tests/e2e/manual-apply-live.spec.ts`
- `frontend/tests/e2e/steering-live.spec.ts`
- `frontend/tests/e2e/takeover-live.spec.ts`
- `frontend/tests/e2e/api-health.spec.ts`
- `frontend/tests/e2e/auth.spec.ts`

## Known External Constraints

- ATS sites can still require CAPTCHA, email verification, login, or other human steps
- “Working end-to-end” means the product handles those interruptions correctly and can be steered through them
- It does not mean every external ATS flow is permanently hands-off

## Recommended Verification Command

Use Node 20 before running Playwright:

```bash
source ~/.nvm/nvm.sh
nvm use 20
npx playwright test \
  tests/e2e/full-flow.spec.ts \
  tests/e2e/pipeline-e2e.spec.ts \
  tests/e2e/manual-apply-live.spec.ts \
  tests/e2e/steering-live.spec.ts \
  tests/e2e/takeover-live.spec.ts \
  --project=chromium --workers=1
```

## Notes On Test Targeting

- Live application tests depend on real external job posts and may fail if a target posting changes behavior or closes
- Prefer known-good postings that have already produced real submitted entries in the application log
- If a live application test fails, inspect the application log and screenshot before changing product logic; external target drift is common
- The `manual-apply-live` UI spec now verifies the manual-apply page against a real previously submitted session. Fresh ATS submission reproducibility is tracked separately because it is the unstable part of the system.
