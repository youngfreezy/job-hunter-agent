# Project Memory

## Workflow & Principles
- See [workflow.md](workflow.md) for orchestration and task management rules.

## General Rules
- Never write scraping selectors without verifying against live DOM in Playwright/Patchright.
- Test end-to-end before handoff; user should not be first to discover breakage.
- Do not use longer waits as a fix for broken behavior; find root cause.
- No silent simulation/mock fallback in production paths.
- Use root `npm start` for fullstack startup.
- No AI attribution in commit messages.
- Anthropic SDK: do not use OpenAI-only `response_format`.

## Frontend Patterns
- Include loading skeleton routes (`loading.tsx`) for every page.
- Include route transition indicator in root layout.
- Prefer Formik + Yup for forms and persist critical wizard state.

## Testing Principles
- Prefer live SSE/WebSocket validation; avoid over-reliance on permissive mocks.
- Verify API connectivity in isolation and from UI tests.
- For Playwright strict-mode locators, use stable/explicit selectors.

## ATS Applier Notes
- Ashby resume upload can stall with React spinner; reload + refill strategy.
- Greenhouse reCAPTCHA Enterprise can be unsolved in some flows (HTTP 428); skip path required.
- ATS appliers: `backend/browser/tools/appliers/{ashby,greenhouse,lever,linkedin,indeed,glassdoor,ziprecruiter,workday}.py`.
