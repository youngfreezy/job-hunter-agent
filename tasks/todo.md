# Task Plan

## Current Run
- [x] Commit verified steering/integration fixes and push to `main`
- [x] Save user-provided workflow/project memory into persistent memory
- [x] Run live (non-mock) Playwright integration tests for steering and pipeline checkpoints
- [x] Verify backend/frontend startup and streaming paths in live environment
- [x] Run extended live automated application + manual intervention scenario
- [x] Verify manual-apply log shows submitted jobs with cover letter + tailored resume
- [x] Validate full UI workflow using iCloud resume file and confirm real submitted job on UI

## Review
- Live tests passed:
  - `frontend/tests/e2e/steering-live.spec.ts`
  - `frontend/tests/e2e/manual-apply-live.spec.ts`
  - `frontend/tests/e2e/pipeline-e2e.spec.ts`:
    - `wizard creates session and coaching events stream`
    - `coach review modal appears and can be approved`
    - `GET session caps scored_jobs to 20`
- Live backend/apply verification passed:
  - `/api/sessions/test-apply` end-to-end with manual intervention streaming (`needs_intervention` -> resume -> submitted)
  - `application-log` persisted submitted entry with non-empty `cover_letter` and `tailored_resume`
- Live UI workflow verification passed:
  - Session started from `/session/new` using `/Users/fareezahmed/Library/Mobile Documents/com~apple~CloudDocs/Resume/Fareez AI Engineer.pdf`
  - Session `5ebabbc4-7efd-4165-aee0-3899a692a6eb` reached real `submitted` application
  - `/session/5ebabbc4-7efd-4165-aee0-3899a692a6eb/manual-apply` displayed submitted row in UI
