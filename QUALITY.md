# Repository quality audit — 2026-10-05

This audit covers the repository inventory, frontend, gateway and storage,
application agents, browser integrations, standalone marketing package, local
tooling, dependencies, and CI. The starting inventory contained 617 tracked files.
Automated searches covered the source tree; manual review concentrated on trust
boundaries, paid work, persistence, shared state, and user entry points. This is
not a claim of line-by-line formal verification or support for every legacy mode.

Review used five axes: correctness, readability, architecture, security, and
performance. A separate reviewer inspected the combined changes and requested
additional deletion fixes before approving them. Behavior changes have regression
coverage. Existing public feature routes and the Browserbase/Stagehand workflow
are preserved; the unsafe experimental direct-API submission path now defaults off.

## Findings addressed

| Severity | Finding | Change |
| --- | --- | --- |
| Critical | Session deletion could remove child data before checking ownership. | Lock and verify the owned parent before any mutation; erase children and parent in one transaction. |
| Required | Account deletion omitted durable sessions, non-cascading schedules/resumes, and published agents; active workers could recreate data. | Transactional cleanup against actual schemas; reject deletion during active, queued, or nonterminal work; revalidate autopilot ownership after admission. |
| Required | An old resume UUID or text from a different cached file could reach a new application. | Revalidate file bytes, retain current attachment state, and update related Formik fields atomically. |
| Required | Corrupt or unavailable browser storage could break upload and launch flows. | One typed storage boundary with safe decoding, TTL validation, and optional persistence; launch from current React state. |
| Required | Draft restoration mutated unchecked stored data and mixed feature policy into a generic hook. | Pure, typed session-draft restoration; explicit per-feature adapter; no restored server attachment identity. |
| Required | Async profile hydration could overwrite newly edited values. | Functional state transitions read the latest values. |
| Required | Required resume errors remained visible after successful async restoration. | Validate one atomic Formik update, then clear loading state. |
| Required | Some controls lacked accessible names/selection state, and a button overflowed at 320px. | Labels, `aria-pressed`, and responsive wrapping; verified rendered layouts. |
| Required | Some provider exceptions were returned to clients. | Fixed public error messages; diagnostic detail stays server-side. |
| Required | Caller-supplied forwarding headers could influence rate-limit identity. | Use authenticated identity or the validated ASGI client; bounded trusted-proxy configuration. Sensitive routes fail closed if Redis is unavailable. |
| Required | Signed SMS webhook handling conflicted with CSRF, XML values were unescaped, and OTP generation was not cryptographic. | Exact signed-webhook exemption, XML escaping, and cryptographic randomness. |
| Required | List endpoints accepted negative pagination values. | Validate lower bounds on query limits and offsets while preserving existing upper caps. |
| Required | URL substring matching misclassified hostile ATS URLs and allowed misleading links. | Canonical parsed-host comparisons, credential rejection, and metadata-only rejection logs. |
| Required | Steering queue reads and deletion were separate operations. | Atomic Redis drain with connection cleanup. |
| Required | Ashby posting cache could retain stale data indefinitely. | Monotonic TTL and bounded capacity. |
| Required | A paid model recounted recorded application statuses. | Pure deterministic counting; no inference or additional model charge. |
| Required | Browser startup cancellation could leak a paid session. | Cleanup also runs on cancellation, then propagates the cancellation. |
| Required | Experimental API submission invented required answers and had unsafe uncertain-result fallback. | `API_APPLY_ENABLED=false`; retain browser path as the default. Re-enabling requires the same fact, receipt, budget, and reconciliation policies. |
| Required | Marketing model output was trusted via a TypeScript cast and rendered into HTML. | Runtime Zod validation, bounded variant count, safe errors, and plain-text HTML encoding. |
| Required | Stop script could kill unrelated processes by port or broad command match. | Recorded PID, checkout, command, and process-identity checks; only owned descendants are stopped. |
| Required | Auth secrets were passed into frontend Docker build arguments. | Supply server auth settings only at runtime; keep public frontend settings as build inputs. |
| Optional | Screenshot frames were decoded twice; effect dependencies were unstable. | Single image decode and stable effect callbacks; no lint warnings. |

Generated duplicate files were preserved outside the checkout with a SHA-256
manifest before removal from the working tree. Dependency lockfiles are included
in builds. CI now checks the local process tooling and standalone marketing
package, in addition to frontend and backend tests.

## Functional and frontend design conventions

- Keep transformations pure: resume draft restoration, URL classification,
  verification counts, and model-output parsing return values without hidden I/O.
- Keep effects at boundaries: storage, browser actions, Redis, database
  transactions, and provider calls have explicit failure paths and ownership.
- Keep related state together. Resume bytes, parsed text, filename, and attachment
  identity represent one transition, not independent updates racing to validate.
- Validate untrusted data once at entry; downstream code uses meaningful types.
  Avoid unchecked casts, fabricated facts, and silent success on persistence failure.
- Reuse existing helpers and remove duplicate work. Extract modules when doing so
  removes concepts or branches, not merely to shorten a file.
- Give async resources a bounded lifecycle: cancellation cleanup, atomic queue
  operations, explicit cache TTL/capacity, and durable submission receipts.

These choices follow [React's purity rules](https://react.dev/reference/rules/components-and-hooks-must-be-pure),
[effect guidance](https://react.dev/learn/you-might-not-need-an-effect), and
[Next.js data security guidance](https://nextjs.org/docs/app/guides/data-security).

## Verification

| Check | Result |
| --- | --- |
| Full backend suite, fresh isolated local PostgreSQL database | 1,055 passed; no skips/ignored tests; 341 existing deprecation warnings |
| Frontend unit suite | 141 passed |
| Frontend lint, TypeScript, production build | Passed |
| Browserbase against local production build, mocked APIs | 39 distinct checks passed across full run and targeted retests; no model calls or applications |
| Responsive checks | Quick Apply and custom search at 320, 768, 1024, and 1440px; no page errors in final sweep |
| Standalone marketing tests and TypeScript build | Four tests passed; build passed |
| Local tooling tests | Three passed, including an actual disposable-process isolation test |
| Whitespace and tracked-file credential-pattern scan | Passed; pattern scan is not a complete Git history/secret audit |
| Independent review | Approved after requested deletion fixes |

Browserbase test sessions were released. Estimated browser cost for the four
mocked UI sessions was $0.007182; model cost was zero. Screenshots and detailed
provider metadata are retained in the local audit artifacts, not committed with
user data. CI and deployment checks are separate release gates, recorded in the
release evidence after the exact committed revision passes.

## Dependency decisions and follow-up

Review date: **2026-10-05**. Reassess remaining advisories by **2026-10-12** and
before exposing new inputs to any affected API. Native audit counts include
packages affected transitively; they are not counts of distinct vulnerabilities.
Tracked in [dependency follow-up #2](https://github.com/youngfreezy/job-hunter-agent/issues/2).

- **Frontend:** upgraded Vitest 3.2.7 to 4.1.11 after reading its migration notes
  and security advisory; changed its config to native ESM. Tests remained green.
  Eight high audit entries remain in the `braces` build/lint dependency graph
  ([GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)).
  No patched braces release was available. These paths consume repository-controlled
  build globs, not HTTP inputs. Keep build configuration trusted; do not force npm's
  suggested framework/lint downgrade. Upgrade when a compatible fix is available.
- **Marketing package:** patched form-data (2.5.6 / 4.0.6) and nanoid (3.3.20) in
  the lockfile. Seven audit entries remain: five low, one moderate, one high.
  The AI SDK 4 dependency tree includes jsondiffpatch HTML/prototype advisories,
  attachment/download advisory paths, and an esbuild Windows development-server
  advisory. This package only uses plain `generateText`; it does not use streaming
  UI diffs, file attachments/downloads, or an esbuild server. Keep those APIs unused
  until a separately tested AI SDK migration resolves the graph. Model output now
  has a validated and HTML-encoded boundary regardless of SDK version.
- **Python:** pip-audit found no known vulnerabilities in the installed audit
  runtime. The requirements still contain version ranges; this result is not a
  guarantee for all future resolutions. Produce and maintain resolved production
  constraints in a separate build-reproducibility change.

Optional architectural follow-ups require dedicated parity tests: split the large
session page into subscription/control orchestration and review panels; separate
transport/auth from feature API clients; consolidate duplicate result pages; and
retire unused agent modes before extracting a typed application policy. Those
changes are intentionally separate from this correctness-focused cleanup. Track
them with acceptance criteria instead of a cosmetic repository-wide rewrite.
See [architecture follow-up #3](https://github.com/youngfreezy/job-hunter-agent/issues/3).

Dependency review sources: [Vitest migration](https://vitest.dev/guide/migration/),
[Vitest advisory](https://github.com/vitest-dev/vitest/security/advisories/GHSA-82fw-gwwq-j7x9),
[form-data 4.0.6](https://github.com/form-data/form-data/releases/tag/v4.0.6),
[form-data 2.5.6](https://github.com/form-data/form-data/releases/tag/v2.5.6),
[nanoid 3.3.20](https://github.com/ai/nanoid/releases/tag/3.3.20).
