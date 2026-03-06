# Lessons

## 2026-03-06

### User correction
- Apply workflow/project-memory rules in the same run they are introduced.
- Prioritize live integration testing over mock-based validation.
- Use `nvm use` to ensure Node 20+ before running frontend/root scripts.

### Prevention rules
- For feature verification, default to real backend/frontend integration tests first.
- If a mock-based test exists, treat it as supplemental only and explicitly run non-mock checks before sign-off.
- Track plan/progress/review in `tasks/todo.md` for non-trivial tasks.
- Before `npm run start` or Playwright runs, assert Node version with `nvm use 20` (or project-required version).
- For live browser streaming, verify the actual image decode path and click-coordinate mapping against a real rendered frame; a visible `<img>` tag is not proof that takeover input will land correctly.
