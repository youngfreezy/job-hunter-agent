# Application boundaries

The application keeps decisions pure where practical and performs effects at
explicit browser, model, storage, and UI boundaries. These boundaries preserve the
existing feature routes and application workflow; they do not introduce a second
execution engine.

## Session UI

`frontend/src/app/(session)/session/[id]/page.tsx` composes the run screen.
`components/session/use-session-run.ts` owns subscriptions, polling, approval
commands, answer saves, and their cleanup. `session-events.ts` and
`presentation.ts` calculate state and display values without network calls.
Focused panels render coaching, shortlist review, application progress, saved
questions, login intervention, chat, and checkpoints.

Approval references still protect against older polling/stream responses. Answer
saves are serialized and read current rules before writing. Submission uncertainty
remains distinct from confirmed delivery. Browserbase Live View stays attached to
the current provider session. These behaviors are covered by unit contracts and
mocked browser workflows.

Career Pivot and Interview Prep share result components. Their route controllers
retain their own creation, reconnection, payment, and navigation decisions. The
landing page renders static sections on the server; FAQ, calculator, and waitlist
interactions use small client components.

## Frontend API

`frontend/src/lib/api.ts` remains the public import path. Its feature modules live
under `lib/api/`: sessions, profile, Browserbase, billing, autopilot, trial,
marketplace, and developer tools.

- `auth.ts` owns the token cache and reads current CSRF cookies for each request.
- `transport.ts` performs one fetch and shares rate-limit notices. It never
  automatically retries a mutation.
- `streams.ts` owns session event routing and cleanup over the reconnecting
  authenticated event source. Trial streams supply only their trial token.
- Feature clients own payloads, return types, and endpoint-specific errors.

No credentials are placed in stream URLs. File uploads leave multipart boundaries
to the browser. Checkpoints and skipped jobs use the same authenticated transport
as the other owner-restricted session reads.

## Application policies and effects

`backend/orchestrator/application_policy.py` contains typed, deterministic policy
for API eligibility, browser concurrency, company batching, outcome classification,
completed jobs, retries, and supervisor fallbacks. It imports no environment
settings and makes no browser, model, or storage calls. Callers supply a policy
snapshot and perform the selected effects.

The application agent uses one settlement path for single and concurrent browser
results. It retains completed receipts and pending questions before a batch pause.
Budget/history failures take priority over an ordinary supervisor pause, and
cancellation propagates after completed work is settled.

Indeed Easy Apply continues to use one managed browser tab and shared auth.
Browserbase runs the browser; Stagehand performs page actions behind the existing
cache and spending controls. Model judgment cannot override confirmed receipts,
unknown delivery, spending reservations, or missing-history holds.

The experimental direct ATS API path stays disabled by default. If enabled, a
POST with ambiguous delivery produces an uncertainty hold instead of a second
submission through the browser. Confirmed receipts and uncertainty holds are
excluded from automatic retry selection.

## Reproducible dependencies

`backend/requirements.in` is the reviewed input; generated production/test locks
pin versions and artifact hashes for Python 3.11 and 3.12. Docker and CI install
hashed wheels and check dependency consistency. Optional legacy integrations stay
outside the production lock. See [dependency maintenance](backend/DEPENDENCIES.md).

`packages/marketing-agent` is a separate ESM package with exact AI SDK/provider
pins, Node 22+ support, and Node 24 CI. Its model responses pass Zod validation and
HTML encoding. Mocked wire-contract tests and compiled library/CLI tests verify
the upgrade without paid model calls.

## Verification boundaries

Unit and backend tests use mocks and disposable local databases. Browserbase UI
tests run the local production build with all application APIs intercepted; they
exercise controls and error recovery without submitting real applications.
Deployment readiness, public routes, responsive rendering, and demo media are
checked separately on the exact released revision. Those checks do not replace
a live application receipt or prove that every employer form will succeed.
