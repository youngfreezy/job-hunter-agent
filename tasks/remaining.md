# Remaining Tasks

## Next.js Refactor
- [ ] Refactor frontend to Next.js Server Components
- [ ] Migrate client-side data fetching to server-side where possible
- [ ] Convert pages/layouts to async Server Components
- [ ] Move client interactivity into smaller `"use client"` leaf components
- [ ] Verify SSE/streaming still works correctly after refactor

## Audit Findings
- [ ] Review and document all audit findings
- [ ] Prioritize findings by severity
- [ ] Create remediation plan for each finding
- [ ] Implement fixes
- [ ] Verify fixes resolve findings

## Security Audit
- [ ] Conduct security audit of backend API endpoints
- [ ] Review authentication/authorization flows
- [ ] Check for OWASP top 10 vulnerabilities
- [ ] Audit secrets management and env var handling
- [ ] Review dependency vulnerabilities (`pip audit`, `npm audit`)
- [ ] Document findings and remediation steps

## Deploy
- [ ] Finalize production deployment configuration
- [ ] Set up CI/CD pipeline
- [ ] Configure production environment variables
- [ ] Deploy backend to production
- [ ] Deploy frontend to production
- [ ] Verify production deployment end-to-end

## Blue-Green Deployments
- [ ] Design blue-green deployment strategy
- [ ] Set up dual environment infrastructure
- [ ] Configure traffic switching mechanism
- [ ] Implement health checks for environment validation
- [ ] Test rollback procedure
- [ ] Document blue-green deployment runbook

## Test Environment
- [ ] Set up dedicated test/staging environment
- [ ] Configure test database and Redis instances
- [ ] Set up test environment env vars and secrets
- [ ] Ensure test environment mirrors production config
- [ ] Automate test environment provisioning
- [ ] Document test environment setup and access
