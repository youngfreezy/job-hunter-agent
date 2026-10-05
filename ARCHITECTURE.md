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

Stagehand discovers each control through `observe`; the app does not invent a
fallback selector. The returned action is checked against the current native
snapshot, audited for applicant facts, and executed through Stagehand's locator
API on that exact target. This deliberately prevents an approved action from
self-healing into a different, unaudited control. An absent or ambiguous target
before execution is a technical state change, not a question for the applicant.
It permits one fresh Stagehand plan before submission intent; a second mismatch
stops the run. Once submission intent is recorded, an uncertain result retains
its hold and cannot trigger another action attempt.

Stagehand owns the next-step judgment, including whether the form is still
loading. Application code does not classify loading pages from button names.
A fresh `wait` decision can be reused only when native snapshots before and
after that decision match, along with the tab, URL, and CAPTCHA generation.
The snapshot fingerprint ignores ephemeral node IDs but retains labels, values,
and structure. Any change requires a fresh, uncached Stagehand assessment.
Unchanged loading screens use native polling instead of repeated model calls.

While Browserbase reports an active CAPTCHA solve, the application waits for its
lifecycle events without page mutations or model polling. Solver completion
triggers a fresh Stagehand assessment; one visual read helps distinguish a
blocking challenge from hidden widget markup. Completion alone never authorizes
submission. Visual decisions are not cached using accessibility-tree identity.
An unchanged CAPTCHA decision based only on the native page can be reused for
passive waiting, bound to the tab, URL, snapshot, solver generation, and active
state. A changed observation requires fresh judgment. These waits share the
existing deadline and retain the time reserved for submission and its receipt.
This uses Browserbase's [solver lifecycle events](https://docs.browserbase.com/platform/identity/captcha-solving)
and Stagehand's [visual extraction](https://docs.stagehand.dev/v4/basics/extract#visual-extract).

Recovery remains a bounded application policy: one GET of the same observed
page, before any submission attempt, with sufficient time for recovery and
receipt verification. It rechecks the observation before navigating and defers
to managed verification. Recovery invalidates the uploaded-resume proof, so the
canonical file and final factual review must be verified again. A loading page,
a successful SDK command, or a solver-finished event is never a submission receipt.

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
