# Startup Packaging Plan

Last updated: March 7, 2026

## Problem

The current startup path is terminal-first:

```bash
source ~/.nvm/nvm.sh
nvm use 20
npm run start
```

That is acceptable for development and live verification, but it is bad product UX. A normal user should not need to know about Node versions, terminal sessions, backend ports, or Docker lifecycle.

## UX Target

The target startup experience is:

1. User double-clicks the app or clicks a single launcher.
2. The app verifies prerequisites silently.
3. Required services start automatically.
4. The UI opens automatically.
5. If something fails, the user sees a product-grade error screen, not shell output.

## Recommendation

Recommended path: `macOS app wrapper first`, then `cross-platform packaged runner`.

Reason:
- The current active environment is macOS.
- The product already depends on local browser automation and local runtime coupling.
- A macOS-first wrapper gives the biggest UX improvement with the least architectural churn.
- A one-click shell script is useful as an intermediate step, but it is still terminal-adjacent rather than consumer-grade.

## Phased Plan

### Phase 1: One-Click Local Launcher

Goal:
- Remove manual shell steps for internal/dev users immediately.

Deliverables:
- `scripts/start-app.sh`
- `scripts/stop-app.sh`
- optional `scripts/restart-app.sh`

Behavior:
- load `nvm`
- select Node 20 automatically
- verify Python venv exists
- verify Docker is running
- start root `npm run start`
- wait for backend/frontend health
- open `http://localhost:3000`
- write logs to a predictable app-runtime directory

Success criteria:
- one command starts the full stack
- no manual `nvm use` step
- no manual browser navigation

### Phase 2: macOS Double-Click Launcher

Goal:
- ship a real desktop-style launch experience on macOS.

Deliverables:
- Automator app, AppleScript app, or lightweight native wrapper
- app icon
- startup status window
- graceful shutdown action

Current status:
- Implemented as `JobHunter Agent.app` at the repo root
- `scripts/build-macos-app.sh` installs the bundle into `~/Applications`
- The bundle launches the existing runtime through Terminal so Finder startup works reliably on macOS without requiring the user to type commands

Behavior:
- user launches `JobHunter Agent.app`
- wrapper runs the same startup script as Phase 1
- frontend opens automatically
- errors are surfaced in a simple UI dialog

Success criteria:
- no terminal required for normal startup
- user can start and stop the app like a desktop product

### Phase 3: Runtime Packaging Cleanup

Goal:
- reduce local-environment fragility before broader packaging.

Deliverables:
- single runtime directory for logs, PID files, temp data
- clear health endpoints for frontend/backend/dependencies
- startup lock to avoid duplicate app instances
- env validation on boot with user-friendly failures

Needed cleanup:
- remove assumptions that the user started from a shell with `nvm` loaded
- make backend/frontend/service startup deterministic
- ensure Chrome/CDP lifecycle is launcher-safe

Success criteria:
- startup is idempotent
- duplicate launches do not create broken multi-process state
- failures are diagnosable without reading terminal output

### Phase 4: Cross-Platform Packaged Runner

Goal:
- prepare for broader distribution and OSS readiness.

Options:
- Electron shell around the Next.js app
- Tauri shell if footprint matters more than Node-native integration
- packaged local orchestrator plus browser UI

Requirements before this phase:
- startup scripts already reliable
- backend/service lifecycle already normalized
- secrets/config flow defined clearly

Success criteria:
- installable app package
- user does not manually manage Node, Python, or shell scripts

## Architecture Decision

Do not start with Electron.

Reason:
- it adds packaging complexity before runtime lifecycle is clean
- the main UX problem right now is startup orchestration, not rendering
- Phase 1 plus Phase 2 solve the immediate problem faster

## Required Startup Behaviors

Any launcher implementation should handle all of the following:

- verify Node version automatically
- verify Python backend environment automatically
- verify Docker availability automatically
- start only one instance of the app stack
- wait for frontend and backend readiness
- open the app in the browser automatically
- persist logs outside transient terminal state
- show actionable errors for:
  - missing env vars
  - Docker not running
  - port conflicts
  - failed backend boot
  - failed frontend boot

## Preferred Implementation Order

1. `scripts/start-app.sh` and `scripts/stop-app.sh`
2. health-check + log-dir normalization
3. macOS `.app` wrapper around the startup script
4. duplicate-instance protection
5. packaged distribution work

## What This Does Not Solve Yet

- full production deployment
- full standalone OSS packaging
- remote/browser-worker architecture packaging
- ATS stability issues

This plan is strictly about startup UX and launcher quality.
