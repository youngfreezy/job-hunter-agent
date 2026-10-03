# JobHunter Agent: Browserbase rebuild (started 2026-10-03)

## Done (local, branch browserbase-mode)
- [x] BROWSER_MODE=browserbase: backend/browser/browserbase_client.py (REST, httpx), settings in shared/config.py,
      BrowserManager.start_browserbase / start_for_task / new_context / stop in backend/browser/manager.py.
- [x] Persisted logins via Browserbase Contexts, mapped per board with BROWSERBASE_CONTEXT_IDS.
- [x] Media blocking in Browserbase mode (saves proxy bytes).
- [x] SSE event browser_live_view emitted by the application node when a cloud session starts.
- [x] tests/test_browserbase_mode.py (6 tests). Live check passed 2026-10-03: manager opened
      myjobs.indeed.com/saved signed in through the persisted Indeed context (PPID cookie present).
- [x] Repo boots locally: uv venv (Python 3.12), docker compose postgres+redis, 159 unit tests pass.

## Next (cloud agent) — worked 2026-10-03, see tasks/review.md
- [x] Fix the 5 failing tests in tests/test_gmail_persistence.py (redis mock) and the 8 errors in
      tests/test_double_submit_prevention.py (DB fixture). Both predate this work.
- [x] Application policy: a free-text "application rules" field per user (model + alembic migration +
      API + Settings UI textarea). Inject it into the scoring prompt (orchestrator/agents/scoring.py) and the
      form filler prompt (backend/browser/tools/form_filler.py FORM_ANALYSIS_PROMPT) so the owner can paste the
      rules they give a coding assistant: eligibility (location, seniority, stack, pay), standard answers,
      park conditions (AI-attestation questions, own-voice essays), and never-invent-facts.
- [x] Discovery: add a Browserbase Fetch API verifier (POST /v1/fetch, markdown) that confirms a requisition is
      open and has an Apply control before it enters the shortlist. Store the verdict on the JobListing.
- [x] Frontend: render the browser_live_view SSE event as an iframe panel in the session view (the Live View
      URL is embeddable), replacing the screenshot feed when provider == browserbase.
- [x] Settings UI: Browserbase section (API key, project id, proxies toggle, per-board Context ids) and a
      "Sign in to <board>" flow that opens a persisted-context session's Live View for the user to log in,
      then stores the Context id (mirror of ~/Desktop/browserbase-demo/login-capture.mjs, as a backend route).
- [x] Skyvern: default SKYVERN_ENABLED stays false; Browserbase mode uses the Playwright appliers
      (backend/browser/tools/appliers). Skyvern-credits abort path removed from the application node.
- [x] Indeed applier: backend/browser/tools/appliers has greenhouse, lever, ashby, generic. Add indeed.py
      (Indeed Apply flow on a logged-in context). LinkedIn stays discovery-only (account-ban risk).
      Selectors are UNVERIFIED (TODO(unverified-selectors) in indeed.py); failures name the selector group.
- [x] Dependency refresh: pin versions that moved since April 2026; CI green on GitHub Actions.

## Second cloud pass (2026-10-03, see tasks/review.md "Second cloud pass")
- [x] Listing verifier matched to the published Fetch API reference and checked live.
- [x] Test suite isolated from a developer .env with a real Browserbase key.
- [x] Browserbase Search API as the discovery search backend when SERPER_API_KEY is unset.
- [x] Browserbase mode no longer fails a submit because a CAPTCHA widget is on the page.
- [ ] Live run (Part B): blocked, the app's Anthropic API key has no credit balance. See review.md.

## Rules carried over
- No AI attribution in commit messages (project-memory.md).
- Never write scraping selectors without verifying against the live DOM.
- No silent mock fallback in production paths.

## Interview demo: Stagehand integration (2026-10-03)
- [x] Verify Stagehand v4 with real Browserbase and configured model credentials.
- [ ] Replace Indeed wizard selectors with bounded natural-language actions.
- [ ] Preserve per-user Context, canonical resume, Indeed-only navigation, and verified receipts.
- [ ] Add temporary Browserbase + Stagehand explainer.
- [ ] Test, review, push, deploy, and verify a live Indeed application through the UI.
